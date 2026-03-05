"""
app/scrapers/blog.py
────────────────────
Blog scraper – visits a blog index URL, discovers recent post links,
fetches the full page content of each post, and returns BlogEntry objects.

Designed to slot into the LangGraph pipeline as the "scrape_blogs" node.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AINewsAggregator/1.0; "
        "+https://github.com/yourname/ai-news-aggregator)"
    )
}
REQUEST_TIMEOUT = 15  # seconds


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class BlogEntry:
    """Represents a single scraped blog post."""
    post_url: str
    title: str
    source_name: str
    source_id: str
    published_at: datetime          # best-effort; falls back to now()
    raw_content: str                # full visible text of the page
    scraped_at: datetime = None

    def __post_init__(self):
        if self.scraped_at is None:
            self.scraped_at = datetime.now(tz=timezone.utc)

    @property
    def article_id(self) -> str:
        return hashlib.sha256(f"blog:{self.post_url}".encode()).hexdigest()[:64]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> str | None:
    """GET a URL and return HTML text, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


# def _extract_links(html: str, base_url: str) -> list[str]:
#     """
#     Extract all <a href> links from HTML that look like blog post URLs.
#     Returns absolute URLs on the same domain.
#     """
#     soup  = BeautifulSoup(html, "lxml")
#     base  = urlparse(base_url)
#     links = set()

#     for a in soup.find_all("a", href=True):
#         href = a["href"].strip()
#         abs_url = urljoin(base_url, href)
#         parsed  = urlparse(abs_url)

#         # Keep only same-domain links with a non-trivial path
#         if parsed.netloc == base.netloc and len(parsed.path) > 1:
#             # Strip query strings and fragments for deduplication
#             links.add(parsed._replace(query="", fragment="").geturl())

#     return list(links)
def _extract_links(html: str, base_url: str) -> list[str]:
    """
    Extract all <a href> links from HTML that look like blog post URLs.
    Returns absolute URLs on the same domain.
    """
    soup  = BeautifulSoup(html, "lxml")
    base  = urlparse(base_url)
    links = set()

    # Generic paths to skip — not actual news articles
    SKIP_PATTERNS = [
        "/careers", "/jobs", "/about", "/privacy", "/terms",
        "/legal", "/security", "/contact", "/support",
        "/company", "/team", "/events", "/research",
        "/product", "/pricing", "/login", "/signup",
        "/claude", "/api", "/newsroom", "/policy",
        "/constitution", "/transparency", "/index",
        "/learning", "/education", "/economic-futures",
        "/economic_futures", "/economicfutures",
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        abs_url = urljoin(base_url, href)
        parsed  = urlparse(abs_url)

        if parsed.netloc != base.netloc:
            continue
        if len(parsed.path) <= 1:
            continue

        # Skip non-article pages
        if any(parsed.path.lower().startswith(p) for p in SKIP_PATTERNS):
            continue

        # For anthropic.com only keep /news/ paths
        if "anthropic.com" in parsed.netloc:
            if "/news/" not in parsed.path:
                continue

        links.add(parsed._replace(query="", fragment="").geturl())

    return list(links)


def _extract_page_text(html: str) -> tuple[str, str]:
    """
    Extract (title, visible_text) from an HTML page.
    Returns visible body text – good enough for LLM summarisation.
    """
    soup  = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title else "Untitled"

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    lines   = [l for l in text.splitlines() if l.strip()]
    cleaned = "\n".join(lines)
    return title, cleaned


def _guess_published_date(html: str) -> datetime:
    """
    Try common meta tags / JSON-LD to find a published date.
    Falls back to now() in UTC.
    """
    from datetime import datetime
    import re, json

    soup = BeautifulSoup(html, "lxml")

    # 1. <meta property="article:published_time" …>
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if "published" in prop.lower():
            content = meta.get("content", "")
            try:
                dt = datetime.fromisoformat(content.rstrip("Z"))
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

    # 2. JSON-LD datePublished
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and "datePublished" in data:
                dt = datetime.fromisoformat(data["datePublished"].rstrip("Z"))
                return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    return datetime.now(tz=timezone.utc)


def _is_recent(dt: datetime, hours: int) -> bool:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return dt >= cutoff


# ── Core scrape functions ──────────────────────────────────────────────────────

def scrape_blog(source: dict, hours: int = 24) -> list[BlogEntry]:
    """
    Scrape a blog index URL for recent posts.
    source keys: id, name, url
    """
    source_id   = source["id"]
    source_name = source["name"]
    index_url   = source["url"]

    logger.info("Scraping blog: %s (%s)", source_name, index_url)

    index_html = _fetch_html(index_url)
    if not index_html:
        logger.error("  Could not fetch index page for %s", source_name)
        return []

    candidate_links = _extract_links(index_html, index_url)
    logger.info("  Found %d candidate links on index page", len(candidate_links))

    entries: list[BlogEntry] = []

    for link in candidate_links:
        html = _fetch_html(link)
        if not html:
            continue

        published_at = _guess_published_date(html)

        if not _is_recent(published_at, hours):
            continue

        title, raw_content = _extract_page_text(html)

        if len(raw_content) < 200:          # skip stub pages
            continue

        logger.info("  ✓ [%s] %s  (%d chars)", published_at.date(), title[:60], len(raw_content))

        entries.append(BlogEntry(
            post_url=link,
            title=title,
            source_name=source_name,
            source_id=source_id,
            published_at=published_at,
            raw_content=raw_content,
        ))

    logger.info("  Blog '%s' → %d recent post(s)", source_name, len(entries))
    return entries


def scrape_blogs(sources: list[dict], hours: int = 24) -> list[BlogEntry]:
    """
    Scrape all blog sources.
    Filters sources to only those with source_type == 'blog'.
    """
    from app.models.database import SourceType

    blog_sources = [s for s in sources if s.get("source_type") == SourceType.blog]
    all_entries: list[BlogEntry] = []

    for source in blog_sources:
        try:
            entries = scrape_blog(source, hours=hours)
            all_entries.extend(entries)
        except Exception as exc:
            logger.error("Failed to scrape blog %s: %s", source.get("name"), exc)

    logger.info("Blog scraper total: %d post(s) found", len(all_entries))
    return all_entries