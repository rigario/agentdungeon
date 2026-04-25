"""Combat cleanup — recover stale active combats after server restart.

On startup, scan for active combats that were left in an inconsistent state
due to crashes or crashes mid-combat. Resolve them automatically:
  • Character HP ≤ 0 → status = 'defeat'
  • All enemy participants dead → status = 'victory'
  • Character missing/orphaned → status = 'aborted' + delete orphaned combat

This is defensive cleanup — it does NOT affect ongoing healthy combats.
"""

from __future__ import annotations

import sqlite3
from typing import Optional
from ..services.database import get_db


def _char_hp(conn: sqlite3.Connection, character_id: str) -> Optional[int]:
    row = conn.execute(
        "SELECT hp_current FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    return row["hp_current"] if row else None


def _enemy_alive_count(conn: sqlite3.Connection, combat_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM combat_participants "
        "WHERE combat_id = ? AND participant_type = 'enemy' AND status = 'alive'",
        (combat_id,),
    ).fetchone()
    return row["cnt"]


def cleanup_stale_combats() -> dict:
    """Scan for and resolve stale active combats.

    Returns: {"resolved": int, "details": [str]} with count and per-combat log.
    """
    conn = get_db()
    resolved = 0
    details = []

    try:
        # Fetch all active combats
        active_combats = conn.execute(
            "SELECT id, character_id, encounter_name, location_id FROM combats WHERE status = 'active'"
        ).fetchall()

        for combat in active_combats:
            cid = combat["character_id"]
            combat_id = combat["id"]
            encounter_name = combat["encounter_name"] or "Combat"

            # Check 1: Does character still exist?
            char_row = conn.execute(
                "SELECT id, name, hp_current FROM characters WHERE id = ?", (cid,)
            ).fetchone()
            if char_row is None:
                # Orphaned combat — resolve as aborted and delete
                conn.execute("UPDATE combats SET status = 'aborted' WHERE id = ?", (combat_id,))
                conn.execute("DELETE FROM combat_participants WHERE combat_id = ?", (combat_id,))
                conn.commit()
                resolved += 1
                details.append(
                    f"combat={combat_id} ORPHANED (character missing) → status='aborted', removed"
                )
                continue

            # Check 2: Is character dead?
            hp_current = char_row["hp_current"]
            if hp_current <= 0:
                conn.execute("UPDATE combats SET status = 'defeat' WHERE id = ?", (combat_id,))
                # Also log the automatic defeat
                conn.execute(
                    "INSERT INTO event_log (character_id, event_type, location_id, description) "
                    "VALUES (?, 'combat_defeat_auto', ?, ?)",
                    (cid, combat["location_id"], f"[Recovery] Combat '{encounter_name}' auto-resolved as defeat (character HP ≤ 0)."),
                )
                conn.commit()
                resolved += 1
                details.append(
                    f"combat={combat_id} character={cid} HP={hp_current} → status='defeat'"
                )
                continue

            # Check 3: Are all enemies dead? → victory
            alive_enemies = _enemy_alive_count(conn, combat_id)
            if alive_enemies == 0:
                # Award victory rewards (minimal — XP/gold tracking handled by combat log,
                # but we must resolve combat state to prevent re-entry)
                conn.execute("UPDATE combats SET status = 'victory' WHERE id = ?", (combat_id,))
                conn.execute(
                    "INSERT INTO event_log (character_id, event_type, location_id, description) "
                    "VALUES (?, 'combat_victory_auto', ?, ?)",
                    (cid, combat["location_id"], f"[Recovery] Combat '{encounter_name}' auto-resolved as victory (no enemies alive)."),
                )
                conn.commit()
                resolved += 1
                details.append(
                    f"combat={combat_id} character={cid} enemies_all_dead → status='victory'"
                )
                continue

            # Otherwise: combat is truly active. No action.
            details.append(
                f"combat={combat_id} character={cid} HP={hp_current} enemies_alive={alive_enemies} → ACTIVE (no cleanup)"
            )

        if resolved > 0:
            conn.commit()
        return {"resolved": resolved, "details": details}

    finally:
        conn.close()
