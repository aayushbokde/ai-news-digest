"""
Test script for YouTube scraper.

Run this to test fetching latest videos from YouTube channels.
"""

import sys
import json
from datetime import datetime
from app.scrapers.youtube import YouTubeScraper


def main():
    """Test YouTube scraper with example channels."""
    
    # Example YouTube channel IDs
    # These are real channels for testing (you can replace with your own)
    TEST_CHANNELS = {
        "OpenAI": "UCXuqSBlHAE6Xw-yeJA7Ufg",          # OpenAI official
        "Anthropic": "UCzx-pFKUC1Yv2o0bPVeEVjQ",      # Anthropic official
        "3Blue1Brown": "UCYO_jab_esuFRV4b17AJtAw",   # 3Blue1Brown (popular AI/math channel)
    }
    
    print("=" * 80)
    print("YouTube Scraper Test")
    print("=" * 80)
    print(f"Testing with {len(TEST_CHANNELS)} channels...")
    print()
    
    # Test 1: Fetch videos from single channel without transcripts (fast)
    print("TEST 1: Fetch latest videos (last 24 hours) - NO TRANSCRIPTS")
    print("-" * 80)
    
    for channel_name, channel_id in TEST_CHANNELS.items():
        print(f"\nFetching from {channel_name} ({channel_id})...")
        
        try:
            videos = YouTubeScraper.fetch_latest_videos(
                channel_id=channel_id,
                hours=24,
                fetch_transcript=False  # Don't fetch transcripts for speed
            )
            
            print(f"  ✓ Found {len(videos)} videos in the last 24 hours")
            
            for i, video in enumerate(videos, 1):
                print(f"\n  Video {i}:")
                print(f"    Title: {video.title}")
                print(f"    Video ID: {video.video_id}")
                print(f"    URL: {video.url}")
                print(f"    Published: {video.published_at.isoformat()}")
                print(f"    Description: {video.description[:100]}..." if len(video.description) > 100 else f"    Description: {video.description}")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print("\n" + "=" * 80)
    print("TEST 2: Fetch with transcripts (SLOWER - commented out)")
    print("-" * 80)
    print("""
To test transcript fetching, uncomment the code below:

    videos = YouTubeScraper.fetch_latest_videos(
        channel_id="UCXuqSBlHAE6Xw-yeJA7Ufg",  # OpenAI
        hours=24,
        fetch_transcript=True  # This will fetch transcripts (slower)
    )
    
    for video in videos:
        if video.transcript:
            print(f"Transcript (first 200 chars): {video.transcript[:200]}...")
    """)
    
    print("\n" + "=" * 80)
    print("TEST 3: Fetch from multiple channels at once")
    print("-" * 80)
    
    print("\nFetching from all test channels...")
    results = YouTubeScraper.fetch_multiple_channels(
        channel_ids=list(TEST_CHANNELS.values()),
        hours=24,
        fetch_transcript=False
    )
    
    total_videos = sum(len(videos) for videos in results.values())
    print(f"✓ Total videos found: {total_videos}")
    
    for channel_name, channel_id in TEST_CHANNELS.items():
        count = len(results[channel_id])
        print(f"  - {channel_name}: {count} video(s)")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("-" * 80)
    print("""
1. To use your own YouTube channels:
   - Get your channel ID from: https://youtube.com/{@your_channel} or settings
   - Replace the TEST_CHANNELS dict with your channels
   - Run this script again

2. To fetch transcripts:
   - Set fetch_transcript=True in your calls
   - Note: This will be slower since it requires additional requests per video

3. To integrate with the database:
   - Create app/models.py with SQLAlchemy models (Source, Article)
   - Create app/database.py with database session management
   - Modify the scraper calls to save results to the database

4. To schedule this automatically:
   - Create app/scheduler.py using APScheduler
   - Run this scraper every 30 minutes or as needed
    """)
    
    print("=" * 80)


if __name__ == "__main__":
    main()
