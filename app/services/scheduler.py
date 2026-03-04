"""
app/services/scheduler.py
──────────────────────────
Runs the aggregator pipeline on a configurable cron schedule.
The cron expression is read from DIGEST_CRON in .env (default: 08:00 UTC daily).
"""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.agent.graph import run_pipeline

logger = logging.getLogger(__name__)


def _job() -> None:
    logger.info("Scheduler triggered – running pipeline")
    state = run_pipeline()
    if state["errors"]:
        logger.warning("Pipeline finished with %d error(s):", len(state["errors"]))
        for err in state["errors"]:
            logger.warning("  • %s", err)
    else:
        logger.info("Pipeline finished successfully")


def start_scheduler() -> None:
    """Start the blocking APScheduler. Call this from main.py."""
    scheduler = BlockingScheduler(timezone="UTC")

    # Parse the cron string (e.g. "0 8 * * *") into APScheduler fields
    cron_parts = settings.digest_cron.split()
    if len(cron_parts) == 5:
        minute, hour, day, month, day_of_week = cron_parts
    else:
        logger.warning("Invalid DIGEST_CRON '%s', falling back to 08:00 UTC", settings.digest_cron)
        minute, hour, day, month, day_of_week = "0", "8", "*", "*", "*"

    trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone="UTC",
    )

    scheduler.add_job(_job, trigger, id="daily_digest", replace_existing=True)

    logger.info(
        "Scheduler started – digest will run at cron '%s' (UTC)",
        settings.digest_cron,
    )
    scheduler.start()