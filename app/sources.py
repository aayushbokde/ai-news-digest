"""
app/sources.py
──────────────
Single place to register every source you want to track.

YouTube channel IDs
  → Go to the channel page, View Source, search "channelId"
  → Or: https://commentpicker.com/youtube-channel-id.php

Blog URLs
  → The homepage / blog index URL (we crawl it for new post links)
"""

from app.models.database import SourceType

SOURCES: list[dict] = [
    # ── YouTube channels ────────────────────────────────────────────────────
    {
        "id":          "UCrDwWp7EBBv4NwvScIpBDOA",
        "name":        "Anthropic",
        "source_type": SourceType.youtube_channel,
        "url":         "https://www.youtube.com/feeds/videos.xml?channel_id=UCrDwWp7EBBv4NwvScIpBDOA",
        "channel_id":  "UCrDwWp7EBBv4NwvScIpBDOA",
    },
    {
        "id":          "UCXZCJLdBC09xxGZ6gcdrc6A",
        "name":        "OpenAI",
        "source_type": SourceType.youtube_channel,
        "url":         "https://www.youtube.com/feeds/videos.xml?channel_id=UCXZCJLdBC09xxGZ6gcdrc6A",
        "channel_id":  "UCXZCJLdBC09xxGZ6gcdrc6A",
    },

    # ── Blogs ────────────────────────────────────────────────────────────────
    {
        "id":          "anthropic-blog",
        "name":        "Anthropic Blog",
        "source_type": SourceType.blog,
        "url":         "https://www.anthropic.com/news",
    },
    # {
    #     "id":          "openai-blog",
    #     "name":        "OpenAI Blog",
    #     "source_type": SourceType.blog,
    #     "url":         "https://openai.com/blog",
    # },
]