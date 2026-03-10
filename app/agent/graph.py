"""
app/agent/graph.py
──────────────────
LangGraph pipeline for the AI News Aggregator.

Graph nodes
  1. scrape_youtube   – fetch recent YouTube videos + transcripts
  2. scrape_blogs     – fetch recent blog posts
  3. store_articles   – upsert raw articles into the database
  4. summarise        – LLM summarises each unsummarised article
  5. build_digest     – LLM assembles the final daily digest
  6. send_email       – email the digest to the configured inbox

State flows top-to-bottom; each node receives and returns a PipelineState.
"""

import logging
import uuid
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from app.config import settings
from app.models.database import (
    Article, ArticleStatus, Digest, Source, SourceType,
    create_tables, get_engine, get_session,
)
from app.scrapers.youtube import scrape_youtube_channels
from app.scrapers.blog import scrape_blogs
from app.services.email import send_digest_email
from app.sources import SOURCES
from app.agent.prompts import (
    SYSTEM_PROMPT,
    USER_INSIGHTS,
    ARTICLE_SUMMARY_PROMPT,
    DIGEST_ASSEMBLY_PROMPT,
)

logger = logging.getLogger(__name__)


# ── Pipeline state ─────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    hours: int                          # look-back window
    sources: list[dict]                 # source configs
    scraped_videos: list[Any]           # VideoEntry list
    scraped_posts: list[Any]            # BlogEntry list
    stored_article_ids: list[str]       # DB article IDs that were upserted
    summarised_article_ids: list[str]   # IDs that now have a summary
    digest_id: str                      # ID of the saved Digest row
    digest_markdown: str                # final digest content
    email_sent: bool
    errors: list[str]


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        groq_api_key=settings.groq_api_key,
        temperature=0.3,
    )


def _llm_call(llm, prompt: str) -> str:
    """Single-turn LLM call; returns the response text."""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    return response.content.strip()


# ── Node implementations ───────────────────────────────────────────────────────

def node_scrape_youtube(state: PipelineState) -> PipelineState:
    logger.info("── Node: scrape_youtube ──")
    try:
        videos = scrape_youtube_channels(state["sources"], hours=state["hours"])
        state["scraped_videos"] = videos
        logger.info("Scraped %d YouTube video(s)", len(videos))
    except Exception as exc:
        logger.error("scrape_youtube failed: %s", exc)
        state["errors"].append(f"scrape_youtube: {exc}")
        state["scraped_videos"] = []
    return state


def node_scrape_blogs(state: PipelineState) -> PipelineState:
    logger.info("── Node: scrape_blogs ──")
    try:
        posts = scrape_blogs(state["sources"], hours=state["hours"])
        state["scraped_posts"] = posts
        logger.info("Scraped %d blog post(s)", len(posts))
    except Exception as exc:
        logger.error("scrape_blogs failed: %s", exc)
        state["errors"].append(f"scrape_blogs: {exc}")
        state["scraped_posts"] = []
    return state


def node_store_articles(state: PipelineState) -> PipelineState:
    logger.info("── Node: store_articles ──")
    engine  = get_engine(settings.database_url)
    create_tables(engine)

    stored_ids: list[str] = []

    with get_session(engine) as session:
        # Upsert sources
        for src in state["sources"]:
            existing = session.get(Source, src["id"])
            if not existing:
                session.add(Source(
                    id=src["id"],
                    name=src["name"],
                    source_type=src["source_type"],
                    url=src["url"],
                ))

        # Store YouTube videos
        for video in state.get("scraped_videos", []):
            art_id = video.article_id
            if not session.get(Article, art_id):
                session.add(Article(
                    id=art_id,
                    external_id=video.video_id,
                    source_id=video.channel_id,
                    title=video.title,
                    url=video.url,
                    raw_content=video.transcript,
                    language=video.transcript_language,
                    status=ArticleStatus.pending if video.transcript else ArticleStatus.skipped,
                    published_at=video.published_at,
                ))
                stored_ids.append(art_id)

        # Store blog posts
        for post in state.get("scraped_posts", []):
            art_id = post.article_id
            if not session.get(Article, art_id):
                session.add(Article(
                    id=art_id,
                    external_id=post.post_url,
                    source_id=post.source_id,
                    title=post.title,
                    url=post.post_url,
                    raw_content=post.raw_content,
                    status=ArticleStatus.pending,
                    published_at=post.published_at,
                ))
                stored_ids.append(art_id)

        session.commit()

    state["stored_article_ids"] = stored_ids
    logger.info("Stored %d new article(s) in DB", len(stored_ids))
    return state


def node_summarise(state: PipelineState) -> PipelineState:
    logger.info("── Node: summarise ──")
    llm    = _get_llm()
    engine = get_engine(settings.database_url)
    summarised: list[str] = []

    with get_session(engine) as session:
        # Fetch all pending articles (not just newly stored ones, to handle retries)
        pending = (
            session.query(Article)
            .filter(Article.status == ArticleStatus.pending)
            .all()
        )
        logger.info("  %d article(s) pending summarisation", len(pending))

        for article in pending:
            if not article.raw_content:
                article.status = ArticleStatus.skipped
                continue
            try:
                prompt = ARTICLE_SUMMARY_PROMPT.format(
                    title=article.title,
                    url=article.url,
                    content=article.raw_content[:3000],  # cap context
                )
                summary = _llm_call(llm, prompt)
                article.summary = summary
                article.status  = ArticleStatus.summarised
                summarised.append(article.id)
                logger.info("  ✓ Summarised: %s", article.title[:60])
            except Exception as exc:
                logger.warning("  Failed to summarise %s: %s", article.id[:8], exc)
                state["errors"].append(f"summarise:{article.id[:8]}: {exc}")

        session.commit()

    state["summarised_article_ids"] = summarised
    return state


def node_build_digest(state: PipelineState) -> PipelineState:
    logger.info("── Node: build_digest ──")

    engine = get_engine(settings.database_url)

    with get_session(engine) as session:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=26)
        articles = (
            session.query(Article)
            .filter(
                Article.status == ArticleStatus.summarised,
                Article.published_at >= cutoff,
            )
            .order_by(Article.published_at.desc())
            .limit(50)
            .all()
        )

        if not articles:
            logger.warning("No summarised articles – digest will be empty")
            state["digest_markdown"] = "_No new content found for today._"
            state["digest_id"]       = ""
            return state

        # Build the article summaries block for the prompt
        article_summaries = "\n\n".join(
            f"**{a.title}**\nURL: {a.url}\nSummary: {a.summary}"
            for a in articles[:20] # cap at 20 articles per digest to avoid token limits
        )

        llm    = _get_llm()
        prompt = DIGEST_ASSEMBLY_PROMPT.format(
            user_insights=USER_INSIGHTS,
            article_summaries=article_summaries,
        )
        digest_md = _llm_call(llm, prompt)

        # Persist digest
        digest_id = str(uuid.uuid4())
        session.add(Digest(id=digest_id, content=digest_md))
        session.commit()

        state["digest_markdown"] = digest_md
        state["digest_id"]       = digest_id

        logger.info("Digest built and saved (id=%s, %d chars)", digest_id[:8], len(digest_md))

    return state


def node_send_email(state: PipelineState) -> PipelineState:
    logger.info("── Node: send_email ──")

    if not state.get("digest_markdown"):
        logger.warning("No digest content – skipping email")
        state["email_sent"] = False
        return state

    try:
        send_digest_email(
            digest_markdown=state["digest_markdown"],
            recipient=settings.digest_recipient_email,
            sender=settings.digest_sender_email,
        )
        state["email_sent"] = True
        logger.info("Email sent to %s", settings.digest_recipient_email)

        # Mark digest as sent
        if state.get("digest_id"):
            from datetime import datetime, timezone
            engine = get_engine(settings.database_url)
            with get_session(engine) as session:
                digest = session.get(Digest, state["digest_id"])
                if digest:
                    digest.sent_at = datetime.now(tz=timezone.utc)
                    digest.sent_to = settings.digest_recipient_email
                    session.commit()

    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        state["errors"].append(f"send_email: {exc}")
        state["email_sent"] = False

    return state


# ── Graph assembly ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("scrape_youtube",  node_scrape_youtube)
    graph.add_node("scrape_blogs",    node_scrape_blogs)
    graph.add_node("store_articles",  node_store_articles)
    graph.add_node("summarise",       node_summarise)
    graph.add_node("build_digest",    node_build_digest)
    graph.add_node("send_email",      node_send_email)

    graph.set_entry_point("scrape_youtube")
    graph.add_edge("scrape_youtube", "scrape_blogs")
    graph.add_edge("scrape_blogs",   "store_articles")
    graph.add_edge("store_articles", "summarise")
    graph.add_edge("summarise",      "build_digest")
    graph.add_edge("build_digest",   "send_email")
    graph.add_edge("send_email",      END)

    return graph.compile()


# ── Public entry point ─────────────────────────────────────────────────────────

def run_pipeline(hours: int | None = None) -> PipelineState:
    """
    Run the full aggregator pipeline.
    Returns the final pipeline state.
    """
    graph = build_graph()

    initial_state: PipelineState = {
        "hours":                   hours or settings.scrape_window_hours,
        "sources":                 SOURCES,
        "scraped_videos":          [],
        "scraped_posts":           [],
        "stored_article_ids":      [],
        "summarised_article_ids":  [],
        "digest_id":               "",
        "digest_markdown":         "",
        "email_sent":              False,
        "errors":                  [],
    }

    logger.info("Starting AI News Aggregator pipeline (window=%dh)", initial_state["hours"])
    final_state = graph.invoke(initial_state)
    logger.info(
        "Pipeline complete. Email sent: %s | Errors: %d",
        final_state["email_sent"],
        len(final_state["errors"]),
    )
    return final_state