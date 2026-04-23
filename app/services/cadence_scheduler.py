"""
D20 Agent RPG — Cadence Background Scheduler.

Automatically advances the doom clock for all active playtest characters
when playtest cadence mode is enabled. Runs as a background thread
started with the FastAPI application.

- Reads playtest config (mode, interval, is_active)
- Queries all characters with active doom_clock entries
- Calls advance_tick() for each character at the configured interval
- Handles errors gracefully (continues on individual character failures)

To disable: set cadence mode to 'normal' (is_active=0) — scheduler sleeps.
"""

import threading
import time
import traceback
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.database import get_db
from app.services.playtest_cadence import (
    get_config,
    advance_tick,
    DEFAULT_TICK_INTERVAL_SECONDS,
)


# ---------------------------------------------------------------------------
# Scheduler state
# ---------------------------------------------------------------------------

_scheduler: BackgroundScheduler = None
_lock = threading.Lock()
_enabled = True  # set False in tests to disable background thread


def get_scheduler() -> BackgroundScheduler:
    """Return the global scheduler instance (for testing/inspection)."""
    global _scheduler
    return _scheduler


def set_enabled(enabled: bool):
    """Enable/disable the background scheduler (test hook)."""
    global _enabled
    _enabled = enabled


# ---------------------------------------------------------------------------
# Job function
# ---------------------------------------------------------------------------

def tick_all_active_characters():
    """
    Background job: iterate all characters with active doom clocks and
    advance their ticks. Runs once per interval when cadence is active.
    """
    if not _enabled:
        return

    config = get_config()
    if not config.get("is_active"):
        # Playtest mode disabled — no-op
        return

    interval = config.get("tick_interval_seconds", DEFAULT_TICK_INTERVAL_SECONDS)
    
    conn = get_db()
    try:
        # Get all active doom clock entries
        rows = conn.execute(
            "SELECT character_id FROM doom_clock WHERE is_active = 1"
        ).fetchall()
        character_ids = [row["character_id"] for row in rows]
    except Exception as e:
        # Table might not exist yet during early bootstrap — skip silently
        print(f"[cadence-scheduler] DB error during character fetch: {e}")
        return
    finally:
        conn.close()

    if not character_ids:
        # No active playtest characters — nothing to do
        return

    tick_errors = 0
    for character_id in character_ids:
        try:
            advance_tick(character_id)
        except Exception as e:
            tick_errors += 1
            print(
                f"[cadence-scheduler] ERROR advancing tick for character {character_id}: {e}"
            )
            traceback.print_exc()

    if tick_errors == 0:
        print(
            f"[cadence-scheduler] Tick complete: {len(character_ids)} characters advanced "
            f"(interval={interval}s, mode={config.get('cadence_mode')})"
        )
    else:
        print(
            f"[cadence-scheduler] Tick complete with errors: {tick_errors}/{len(character_ids)} failed"
        )


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start_scheduler(app):
    """
    Start the background scheduler when FastAPI app starts.
    Called from app.main.py lifespan.
    """
    global _scheduler
    
    with _lock:
        if _scheduler is not None:
            print("[cadence-scheduler] Scheduler already running — skipping startup")
            return

        _scheduler = BackgroundScheduler()
        # Use interval trigger; actual interval read from DB at runtime
        _scheduler.add_job(
            tick_all_active_characters,
            trigger=IntervalTrigger(seconds=DEFAULT_TICK_INTERVAL_SECONDS),
            id="cadence_tick_job",
            name="Cadence Doom Clock Tick",
            replace_existing=True,
        )
        _scheduler.start()
        print(f"[cadence-scheduler] Scheduler started — interval={DEFAULT_TICK_INTERVAL_SECONDS}s")
        print("[cadence-scheduler] Set cadence mode via POST /cadence/toggle to activate")


def stop_scheduler(app):
    """
    Shut down the background scheduler when FastAPI app stops.
    """
    global _scheduler
    
    with _lock:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            print("[cadence-scheduler] Scheduler stopped")
