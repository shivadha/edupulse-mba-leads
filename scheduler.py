"""
EduPulse India — Background scheduler
Runs scrapers every 5 minutes, stores results in DB.
"""

import time
import threading
import logging
from datetime import datetime

logger = logging.getLogger("edupulse.scheduler")

_scheduler_thread = None
_stop_event = threading.Event()
_last_run = {"time": None, "added": 0}
_is_running = False


def _run_cycle():
    """Single scrape cycle: run all scrapers + save to DB."""
    import database as db
    from scraper.sources import run_all_scrapers

    logger.info("[Scheduler] Starting scrape cycle at %s", datetime.now().strftime("%H:%M:%S"))
    start = time.time()
    try:
        # health_callback records per-source ok/fail into source_health table
        items = run_all_scrapers(health_callback=db.record_source_health)
        added = db.save_intelligence_batch(items)
        duration = round(time.time() - start, 1)
        db.log_scrape_run(added, duration)
        _last_run["time"] = datetime.now().strftime("%d %b %Y %H:%M:%S")
        _last_run["added"] = added
        logger.info("[Scheduler] Cycle done — %d new items in %.1fs", added, duration)
    except Exception as exc:
        logger.error("[Scheduler] Cycle failed: %s", exc)


def _scheduler_loop(interval_seconds: int):
    global _is_running
    _is_running = True
    logger.info("[Scheduler] Started — interval %ds", interval_seconds)
    while not _stop_event.is_set():
        try:
            _run_cycle()
        except Exception as exc:
            logger.error("[Scheduler] Unhandled error: %s", exc)
        # Wait, but wake early if stop is requested
        _stop_event.wait(interval_seconds)
    _is_running = False
    logger.info("[Scheduler] Stopped.")


def start(interval_seconds: int = 300):
    """Start background scraper thread (every 5 min by default)."""
    global _scheduler_thread
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(interval_seconds,),
        daemon=True,
        name="EduPulse-Scheduler"
    )
    _scheduler_thread.start()


def stop():
    """Signal the scheduler to stop."""
    _stop_event.set()


def status() -> dict:
    return {
        "running": _is_running,
        "last_run": _last_run.get("time") or "Not yet",
        "last_added": _last_run.get("added", 0),
    }
