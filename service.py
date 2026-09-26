"""
EduPulse India — Standalone background scraper service (Phase 1)
=================================================================
Runs the scrape loop as a proper background process — no Flask needed.

Usage:
    python service.py start          # launch daemon in background
    python service.py stop           # stop the daemon
    python service.py status         # is it running?
    python service.py run-once       # single scrape cycle in foreground
    python service.py restart        # stop + start

The daemon writes its PID to data/scraper.pid and logs to data/scraper.log.
Each cycle runs all scrapers with per-source health tracking
(database.record_source_health) and persists intent-scored items.

For production servers, use the provided edupulse-scraper.service
systemd unit instead — it gives you auto-restart and journald logging.
"""

import os
import sys
import time
import signal
import logging
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PID_FILE = os.path.join(DATA_DIR, "scraper.pid")
LOG_FILE = os.path.join(DATA_DIR, "scraper.log")
INTERVAL = int(os.getenv("EDUPULSE_INTERVAL", "300"))  # seconds between cycles


def _setup_logging():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_cycle():
    """One scrape cycle: all sources -> DB, with health tracking."""
    import database as db
    from scraper.sources import run_all_scrapers

    logger = logging.getLogger("edupulse.service")
    logger.info("Starting scrape cycle")
    start = time.time()
    try:
        items = run_all_scrapers(health_callback=db.record_source_health)
        added = db.save_intelligence_batch(items)
        duration = round(time.time() - start, 1)
        db.log_scrape_run(added, duration)
        high = sum(1 for i in items if i.get("intent_level") == "high")
        logger.info("Cycle done — %d new items (%d high-intent) in %.1fs",
                    added, high, duration)
        return added
    except Exception as exc:
        logger.error("Cycle failed: %s", exc)
        return 0


def daemon_loop():
    """Long-running loop executed inside the daemon process."""
    import database as db

    _setup_logging()
    logger = logging.getLogger("edupulse.service")
    db.init_db()
    logger.info("EduPulse scraper daemon started (interval %ds, pid %d)",
                INTERVAL, os.getpid())

    stop = {"flag": False}

    def _handle(sig, frame):
        logger.info("Received signal %s — shutting down", sig)
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    while not stop["flag"]:
        try:
            run_cycle()
        except Exception as exc:  # never let the daemon die on a bad cycle
            logger.error("Unhandled cycle error: %s", exc)
        # sleep in small chunks so SIGTERM is honoured promptly
        for _ in range(INTERVAL):
            if stop["flag"]:
                break
            time.sleep(1)
    logger.info("EduPulse scraper daemon stopped")


# ---------------------------------------------------------------------------
# CLI: start / stop / status / restart / run-once
# ---------------------------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def cmd_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"Already running (pid {pid})")
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    log = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "service.py"), "_daemon"],
        cwd=BASE_DIR,
        stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from this terminal
        close_fds=True,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    print(f"Started scraper daemon (pid {proc.pid}), logging to {LOG_FILE}")


def cmd_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        print("Not running")
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return
    os.kill(pid, signal.SIGTERM)
    # graceful shutdown finishes the current scrape cycle first (~3 min max)
    for _ in range(60):
        if not _pid_alive(pid):
            break
        time.sleep(1)
    else:
        os.kill(pid, signal.SIGKILL)
        print("Force-killed (cycle did not finish in 60s)")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    print(f"Stopped (was pid {pid})")


def cmd_status():
    import database as db
    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"RUNNING (pid {pid})")
    else:
        print("STOPPED")
    try:
        db.init_db()
        h = db.get_source_health()
        ok = sum(1 for s in h if s.get("last_error") is None and s.get("last_ok"))
        print(f"sources tracked: {len(h)}, healthy: {ok}")
        last = db.get_last_scrape_time()
        print(f"last scrape: {last}")
    except Exception as exc:
        print(f"(db check failed: {exc})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "restart":
        cmd_stop()
        time.sleep(2)
        cmd_start()
    elif cmd == "run-once":
        _setup_logging()
        import database as db
        db.init_db()
        added = run_cycle()
        print(f"run-once complete: {added} new items")
    elif cmd == "_daemon":
        daemon_loop()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
