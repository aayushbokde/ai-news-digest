"""
tests/test_youtube_scraper.py
──────────────────────────────
Quick integration test for the YouTube scraper.
Run with:  python -m pytest tests/test_youtube_scraper.py -v
Or simply: python tests/test_youtube_scraper.py
"""

import logging
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

from app.scrapers.youtube import scrape_youtube_channels
from app.sources import SOURCES

TEST_HOURS = 72   # widen window so we're guaranteed to see results


def test_scrape_youtube():
    videos = scrape_youtube_channels(SOURCES, hours=TEST_HOURS)

    print(f"\n{'='*60}")
    print(f"YouTube Scraper – last {TEST_HOURS}h | {len(videos)} video(s) found")
    print(f"{'='*60}\n")

    for v in videos:
        print(f"📺  {v.title}")
        print(f"    Channel  : {v.channel_name}")
        print(f"    URL      : {v.url}")
        print(f"    Published: {v.published_at.strftime('%Y-%m-%d %H:%M UTC')}")
        if v.transcript:
            preview = v.transcript[:300].replace("\n", " ")
            print(f"    Transcript ({v.transcript_language}): {preview}…")
        else:
            print(f"    Transcript: not available")
        print()

    # At minimum the scraper should run without crashing
    assert isinstance(videos, list)


if __name__ == "__main__":
    test_scrape_youtube()