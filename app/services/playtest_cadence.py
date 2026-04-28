"""D20 Agent RPG — Playtest Cadence Mode.

Accelerated tick system for fast validation and demo pacing. In normal mode,
the game advances at real-time pace. In playtest mode, ticks can be shortened
so agents can exercise the full async turn flow, doom-clock progression,
and front advancement in a single session.

Cadence modes:
  - "normal"   — production cadence (default). No accelerated ticks.
  - "playtest" — 3-5 minute ticks. Doom clock advances per tick.
                 Front portents can be triggered by tick thresholds.

The doom clock is a simple per-character counter that increments on each
tick. When it crosses configurable thresholds, it can auto-advance front
portents or trigger narrative events. This lets a deployment validate the full
"DM heartbeat → turn → front advance → doom" loop without waiting days.
"""

import json
import time
import uuid
from datetime import datetime, timedelta
from app.services.database import get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TICK_INTERVAL_SECONDS = 180  # 3 minutes
DEFAULT_DOOM_TICKS_PER_PORTENT = 3   # advance front every 3 ticks
CADENCE_MODES = ("normal", "playtest")


# ---------------------------------------------------------------------------
# Playtest Config
# ---------------------------------------------------------------------------

def get_config() -> dict:
    """Get current playtest cadence configuration."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM playtest_config WHERE id = 1"
    ).fetchone()
    conn.close()
    if not row:
        return {
            "cadence_mode": "normal",
            "tick_interval_seconds": DEFAULT_TICK_INTERVAL_SECONDS,
            "doom_ticks_per_portent": DEFAULT_DOOM_TICKS_PER_PORTENT,
            "is_active": 0,
            "total_ticks": 0,
            "last_tick_at": None,
            "started_at": None,
        }
    return dict(row)


def set_cadence_mode(mode: str, tick_interval: int = None) -> dict:
    """Set the cadence mode. Creates config row if needed."""
    if mode not in CADENCE_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {CADENCE_MODES}")

    is_active = 1 if mode == "playtest" else 0
    conn = get_db()

    # Upsert config
    conn.execute("""
        INSERT INTO playtest_config (id, cadence_mode, tick_interval_seconds,
            doom_ticks_per_portent, is_active, started_at, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            cadence_mode = excluded.cadence_mode,
            tick_interval_seconds = COALESCE(excluded.tick_interval_seconds, playtest_config.tick_interval_seconds),
            is_active = excluded.is_active,
            started_at = CASE WHEN excluded.is_active = 1 AND playtest_config.is_active = 0
                              THEN CURRENT_TIMESTAMP
                              ELSE playtest_config.started_at
                         END,
            updated_at = CURRENT_TIMESTAMP
    """, (
        mode,
        tick_interval or DEFAULT_TICK_INTERVAL_SECONDS,
        DEFAULT_DOOM_TICKS_PER_PORTENT,
        is_active,
        datetime.utcnow().isoformat() if is_active else None,
    ))
    conn.commit()
    conn.close()
    return get_config()


def set_tick_interval(seconds: int) -> dict:
    """Update the tick interval without changing mode."""
    if seconds < 30:
        raise ValueError("Tick interval must be at least 30 seconds")
    conn = get_db()
    conn.execute(
        "UPDATE playtest_config SET tick_interval_seconds = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (seconds,)
    )
    conn.commit()
    conn.close()
    return get_config()


# ---------------------------------------------------------------------------
# Doom Clock
# ---------------------------------------------------------------------------

def get_doom_clock(character_id: str) -> dict:
    """Get doom clock state for a character."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM doom_clock WHERE character_id = ?", (character_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {
            "character_id": character_id,
            "total_ticks": 0,
            "portents_triggered": 0,
            "last_tick_at": None,
            "is_active": 0,
        }
    return dict(row)


def advance_tick(character_id: str) -> dict:
    """Advance the doom clock by one tick for a character.

    Returns the updated doom clock state plus any triggered events
    (e.g., front portent advancement).
    """
    config = get_config()
    if not config["is_active"]:
        return {"error": "Playtest cadence is not active. Toggle to playtest mode first."}

    conn = get_db()
    triggered_events = []
    try:
        # Upsert doom clock
        conn.execute("""
            INSERT INTO doom_clock (character_id, total_ticks, portents_triggered, last_tick_at, is_active)
            VALUES (?, 1, 0, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(character_id) DO UPDATE SET
                total_ticks = doom_clock.total_ticks + 1,
                last_tick_at = CURRENT_TIMESTAMP,
                is_active = 1
        """, (character_id,))
        conn.commit()

        # Read updated state
        row = conn.execute(
            "SELECT * FROM doom_clock WHERE character_id = ?", (character_id,)
        ).fetchone()
        state = dict(row)

        # Check if we should advance a front portent
        ticks_per_portent = config.get("doom_ticks_per_portent", DEFAULT_DOOM_TICKS_PER_PORTENT)
        prev_portents = state["portents_triggered"]
        new_portents = state["total_ticks"] // ticks_per_portent

        if new_portents > prev_portents:
            # Advance active fronts
            fronts = conn.execute(
                "SELECT cf.*, f.name as front_name, f.grim_portents_json "
                "FROM character_fronts cf "
                "JOIN fronts f ON f.id = cf.front_id "
                "WHERE cf.character_id = ? AND cf.is_active = 1",
                (character_id,)
            ).fetchall()

            for front in fronts:
                portents = json.loads(front["grim_portents_json"])
                current_idx = front["current_portent_index"]
                if current_idx < len(portents) - 1:
                    new_idx = current_idx + 1
                    conn.execute(
                        "UPDATE character_fronts SET current_portent_index = ?, advanced_at = CURRENT_TIMESTAMP "
                        "WHERE character_id = ? AND front_id = ?",
                        (new_idx, character_id, front["front_id"])
                    )
                    triggered_events.append({
                        "type": "front_portent_advanced",
                        "front_id": front["front_id"],
                        "front_name": front["front_name"],
                        "old_portent": current_idx,
                        "new_portent": new_idx,
                        "portent_text": portents[new_idx] if new_idx < len(portents) else None,
                        "trigger": f"doom_clock_tick_{state['total_ticks']}",
                    })

            # Update portents_triggered count
            conn.execute(
                "UPDATE doom_clock SET portents_triggered = ? WHERE character_id = ?",
                (new_portents, character_id)
            )

        # Log tick event
        conn.execute(
            "INSERT INTO event_log (character_id, event_type, location_id, description, data_json) "
            "VALUES (?, 'cadence_tick', ?, ?, ?)",
            (
                character_id,
                None,
                f"Playtest tick #{state['total_ticks']}. Doom clock: {state['total_ticks']} ticks, "
                f"{new_portents} portents triggered.",
                json.dumps({"tick": state["total_ticks"], "events": triggered_events}),
            )
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Return updated state
    final_state = get_doom_clock(character_id)
    final_state["triggered_events"] = triggered_events
    final_state["tick_interval_seconds"] = config["tick_interval_seconds"]
    return final_state


def get_cadence_status() -> dict:
    """Full cadence system status — config + global stats."""
    config = get_config()
    conn = get_db()
    doom_stats = conn.execute(
        "SELECT COUNT(*) as chars_with_clock, SUM(total_ticks) as total_ticks_all "
        "FROM doom_clock WHERE is_active = 1"
    ).fetchone()
    conn.close()

    return {
        "config": config,
        "global_stats": {
            "characters_with_doom_clock": doom_stats["chars_with_clock"] or 0,
            "total_ticks_all_characters": doom_stats["total_ticks_all"] or 0,
        },
        "next_tick_eta_seconds": config["tick_interval_seconds"] if config["is_active"] else None,
    }
