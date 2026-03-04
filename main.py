"""
main.py
───────
Entry point for the AI News Aggregator.

Usage:
  # Run the pipeline once right now (useful for testing / manual trigger)
  python main.py --run-now

  # Start the scheduler (runs on the cron defined in .env)
  python main.py --schedule

  # Default (no flag): run once
  python main.py
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Aggregator")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start the scheduler (runs on the configured cron)",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline immediately and exit",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Override the look-back window in hours (default: SCRAPE_WINDOW_HOURS from .env)",
    )
    args = parser.parse_args()

    if args.schedule:
        logger.info("Starting in scheduler mode")
        from app.services.scheduler import start_scheduler
        start_scheduler()  # blocking

    else:
        # Default: run once
        logger.info("Running pipeline once")
        from app.agent.graph import run_pipeline
        state = run_pipeline(hours=args.hours)

        print("\n" + "=" * 60)
        print("Pipeline complete")
        print(f"  Email sent : {state['email_sent']}")
        print(f"  Errors     : {len(state['errors'])}")
        if state["errors"]:
            for err in state["errors"]:
                print(f"    • {err}")
        if state.get("digest_markdown"):
            print("\n── Digest preview (first 500 chars) ──")
            print(state["digest_markdown"][:500])
        print("=" * 60)


if __name__ == "__main__":
    main()