"""
app/scrapers/youtube.py
───────────────────────
YouTube scraper – fetches latest videos from channels via RSS feed
and retrieves transcripts using youtube-transcript-api.

Designed to slot into the LangGraph pipeline as the "scrape_youtube" node.
The node receives a ScrapeState and returns enriched VideoEntry objects.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

logger = logging.getLogger(__name__)

RSS_BASE_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class VideoEntry:
    """Represents a single scraped YouTube video."""
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    published_at: datetime
    url: str
    transcript: str | None = None
    transcript_language: str | None = None

    # Convenience – stable article ID for the DB
    @property
    def article_id(self) -> str:
        return hashlib.sha256(f"yt:{self.video_id}".encode()).hexdigest()[:64]


# ── RSS helpers ────────────────────────────────────────────────────────────────

def _get_channel_feed(channel_id: str) -> list:
    """Fetch and parse the RSS feed for a YouTube channel."""
    url = RSS_BASE_URL.format(channel_id=channel_id)
    feed = feedparser.parse(url)
    if feed.bozo:
        logger.warning("Feed parse issue for %s: %s", channel_id, feed.bozo_exception)
    return feed.entries


def _parse_published_date(entry) -> datetime:
    """Return a timezone-aware UTC datetime from a feed entry."""
    if entry.get("published_parsed"):
        ts = time.mktime(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _filter_recent(entries: list, hours: int) -> list:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    return [e for e in entries if _parse_published_date(e) >= cutoff]


def _extract_video_id(entry) -> str | None:
    video_id = entry.get("yt_videoid")
    if video_id:
        return video_id
    link = entry.get("link", "")
    if "v=" in link:
        return link.split("v=")[-1].split("&")[0]
    return None


# ── Transcript helper ──────────────────────────────────────────────────────────

def _get_transcript(video_id: str) -> tuple[str | None, str | None]:
    """
    Fetch transcript for a video.
    Tries English first, then falls back to any available language.
    Returns (transcript_text, language_code).
    """
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=["en"])
        text = " ".join(s.text for s in fetched.snippets)
        return text, fetched.language_code

    except NoTranscriptFound:
        try:
            fetched = api.fetch(video_id)
            text = " ".join(s.text for s in fetched.snippets)
            return text, fetched.language_code
        except Exception as exc:
            logger.info("No transcript in any language for %s: %s", video_id, exc)
            return None, None

    except TranscriptsDisabled:
        logger.info("Transcripts disabled for video %s", video_id)
        return None, None

    except Exception as exc:
        logger.warning("Transcript fetch failed for %s: %s", video_id, exc)
        return None, None


# ── Core scrape functions ──────────────────────────────────────────────────────

def scrape_channel(channel_config: dict, hours: int = 24) -> list[VideoEntry]:
    """
    Scrape a single YouTube channel for recent videos + transcripts.
    channel_config keys: id, name, channel_id
    """
    channel_id   = channel_config["channel_id"]
    channel_name = channel_config["name"]

    logger.info("Scraping YouTube channel: %s (%s)", channel_name, channel_id)

    all_entries    = _get_channel_feed(channel_id)
    recent_entries = _filter_recent(all_entries, hours=hours)

    logger.info(
        "  %d/%d videos within last %dh",
        len(recent_entries), len(all_entries), hours,
    )

    videos: list[VideoEntry] = []

    for entry in recent_entries:
        video_id = _extract_video_id(entry)
        if not video_id:
            logger.warning("  Could not extract video ID from: %s", entry.get("link"))
            continue

        title        = entry.get("title", "Untitled")
        published_at = _parse_published_date(entry)
        url          = f"https://www.youtube.com/watch?v={video_id}"

        logger.info("  Processing [%s] %s", video_id, title)

        transcript, lang = _get_transcript(video_id)

        if transcript:
            logger.info("    ✓ Transcript (%s) – %d chars", lang, len(transcript))
        else:
            logger.info("    ✗ No transcript")

        videos.append(VideoEntry(
            video_id=video_id,
            title=title,
            channel_name=channel_name,
            channel_id=channel_id,
            published_at=published_at,
            url=url,
            transcript=transcript,
            transcript_language=lang,
        ))

    return videos


def scrape_youtube_channels(sources: list[dict], hours: int = 24) -> list[VideoEntry]:
    """
    Scrape all YouTube channel sources.
    Filters sources to only those with source_type == 'youtube_channel'.
    """
    from app.models.database import SourceType

    yt_sources = [s for s in sources if s.get("source_type") == SourceType.youtube_channel]
    all_videos: list[VideoEntry] = []

    for source in yt_sources:
        try:
            videos = scrape_channel(source, hours=hours)
            all_videos.extend(videos)
        except Exception as exc:
            logger.error("Failed to scrape channel %s: %s", source.get("name"), exc)

    logger.info("YouTube scraper total: %d video(s) found", len(all_videos))
    return all_videos