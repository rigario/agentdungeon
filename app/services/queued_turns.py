"""Queued turn receipts for locked live-tick mode.

This module gives agents immediate proof-of-custody for asynchronous turns:
submit now, process on the next world tick, poll status by turn_id.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import BASE_URL
from app.services.database import get_db
from app.services.playtest_cadence import get_config

DEFAULT_PROCESSING_WINDOW_SECONDS = 120
DEFAULT_CUTOFF_SECONDS = 60

TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}
VALID_STATUSES = {"queued", "processing", *TERMINAL_STATUSES}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_db_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_queued_turns_table(conn=None) -> None:
    """Create queued_turns table/indexes idempotently for new and existing DBs."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS queued_turns (
            turn_id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL,
            message TEXT NOT NULL,
            idempotency_key TEXT,
            session_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            tick_id TEXT NOT NULL,
            next_tick_at TEXT NOT NULL,
            cutoff_at TEXT NOT NULL,
            estimated_processing_window_seconds INTEGER DEFAULT 120,
            result_json TEXT,
            error_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_started_at TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id),
            UNIQUE(character_id, idempotency_key)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queued_turns_character ON queued_turns(character_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queued_turns_status ON queued_turns(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queued_turns_tick ON queued_turns(tick_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queued_turns_next_tick ON queued_turns(next_tick_at)")
    conn.commit()
    if should_close:
        conn.close()


def compute_tick_window(now: datetime | None = None) -> dict[str, str | int]:
    """Compute the next tick/cutoff window from cadence config.

    If cadence has no last_tick_at yet, anchor the next tick at now + interval.
    If the computed cutoff has already passed, roll one interval forward so the
    receipt never promises a closed intake window.
    """
    now = now or utcnow()
    config = get_config()
    interval = int(config.get("tick_interval_seconds") or 900)
    if interval < 30:
        interval = 30
    last_tick = _parse_db_ts(config.get("last_tick_at"))
    next_tick = (last_tick + timedelta(seconds=interval)) if last_tick else (now + timedelta(seconds=interval))
    cutoff = next_tick - timedelta(seconds=DEFAULT_CUTOFF_SECONDS)
    while cutoff <= now:
        next_tick += timedelta(seconds=interval)
        cutoff = next_tick - timedelta(seconds=DEFAULT_CUTOFF_SECONDS)
    tick_id = "tick_" + next_tick.strftime("%Y%m%dT%H%M%SZ")
    return {
        "tick_id": tick_id,
        "next_tick_at": _iso(next_tick),
        "cutoff_at": _iso(cutoff),
        "tick_interval_seconds": interval,
        "estimated_processing_window_seconds": DEFAULT_PROCESSING_WINDOW_SECONDS,
    }


def _latest_portal_url(conn, character_id: str, base_url: str) -> str | None:
    row = conn.execute(
        """
        SELECT token FROM share_tokens
        WHERE character_id = ? AND revoked = 0
          AND (expires_at IS NULL OR expires_at = '' OR expires_at > CURRENT_TIMESTAMP)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (character_id,),
    ).fetchone()
    if not row:
        return None
    return f"{base_url.rstrip('/')}/portal/{row['token']}/view"


def _row_to_status(row, base_url: str | None = None, duplicate: bool = False) -> dict[str, Any]:
    base = (base_url or BASE_URL).rstrip("/")
    status = row["status"]
    result = json.loads(row["result_json"]) if row["result_json"] else None
    error = json.loads(row["error_json"]) if row["error_json"] else None
    if status == "queued":
        message = "Turn accepted. It is queued for the next world tick and has not been lost."
    elif status == "processing":
        message = "Turn accepted; the world tick is processing it now. Keep polling this status_url or watch the portal."
    elif status == "completed":
        message = "Turn completed. The final DM result is attached."
    elif status == "failed":
        message = "Turn failed during tick processing. The error is attached; retry with the same idempotency_key only if instructed."
    else:
        message = f"Turn status is {status}."

    return {
        "accepted": status in {"queued", "processing", "completed"},
        "duplicate": duplicate,
        "status": status,
        "turn_id": row["turn_id"],
        "character_id": row["character_id"],
        "tick_id": row["tick_id"],
        "next_tick_at": row["next_tick_at"],
        "cutoff_at": row["cutoff_at"],
        "estimated_processing_window_seconds": row["estimated_processing_window_seconds"],
        "status_url": f"{base}/turns/{row['turn_id']}/status",
        "portal_url": row["portal_url"] if "portal_url" in row.keys() else None,
        "message": message,
        "instructions": [
            "Your turn has been accepted; do not assume silence means it was dropped.",
            "Poll status_url until status becomes completed or failed.",
            "If you retry after a network error, reuse the same idempotency_key to avoid duplicate turns.",
            "Watch portal_url when present for human-readable state updates.",
        ],
        "result": result,
        "error": error,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "processing_started_at": row["processing_started_at"],
        "completed_at": row["completed_at"],
    }


def _fetch_turn(conn, turn_id: str, base_url: str):
    row = conn.execute(
        """
        SELECT qt.*, (
            SELECT token FROM share_tokens st
            WHERE st.character_id = qt.character_id AND st.revoked = 0
              AND (st.expires_at IS NULL OR st.expires_at = '' OR st.expires_at > CURRENT_TIMESTAMP)
            ORDER BY st.created_at DESC LIMIT 1
        ) AS portal_token
        FROM queued_turns qt
        WHERE qt.turn_id = ?
        """,
        (turn_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["portal_url"] = f"{base_url.rstrip('/')}/portal/{data['portal_token']}/view" if data.get("portal_token") else None
    return data


def enqueue_turn(
    character_id: str,
    message: str,
    idempotency_key: Optional[str] = None,
    session_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a queued turn and return an immediate agent-facing receipt."""
    if not character_id:
        raise ValueError("character_id is required")
    if not message or not message.strip():
        raise ValueError("message is required")

    base = (base_url or BASE_URL).rstrip("/")
    conn = get_db()
    try:
        ensure_queued_turns_table(conn)
        character = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not character:
            raise LookupError(f"character_not_found:{character_id}")

        if idempotency_key:
            existing = conn.execute(
                "SELECT turn_id FROM queued_turns WHERE character_id = ? AND idempotency_key = ?",
                (character_id, idempotency_key),
            ).fetchone()
            if existing:
                row = _fetch_turn(conn, existing["turn_id"], base)
                return _row_to_status(row, base, duplicate=True)

        window = compute_tick_window()
        turn_id = "turn_" + uuid.uuid4().hex[:16]
        conn.execute(
            """
            INSERT INTO queued_turns (
                turn_id, character_id, message, idempotency_key, session_id,
                status, tick_id, next_tick_at, cutoff_at,
                estimated_processing_window_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                turn_id,
                character_id,
                message.strip(),
                idempotency_key,
                session_id,
                window["tick_id"],
                window["next_tick_at"],
                window["cutoff_at"],
                window["estimated_processing_window_seconds"],
            ),
        )
        conn.commit()
        row = _fetch_turn(conn, turn_id, base)
        return _row_to_status(row, base, duplicate=False)
    finally:
        conn.close()


def get_turn_status(turn_id: str, base_url: Optional[str] = None) -> dict[str, Any]:
    base = (base_url or BASE_URL).rstrip("/")
    conn = get_db()
    try:
        ensure_queued_turns_table(conn)
        row = _fetch_turn(conn, turn_id, base)
        if not row:
            raise LookupError(f"turn_not_found:{turn_id}")
        return _row_to_status(row, base)
    finally:
        conn.close()


def mark_turn_processing(turn_id: str, base_url: Optional[str] = None) -> dict[str, Any]:
    return update_turn_status(turn_id, "processing", base_url=base_url)


def mark_turn_completed(turn_id: str, result: dict[str, Any], base_url: Optional[str] = None) -> dict[str, Any]:
    return update_turn_status(turn_id, "completed", result=result, base_url=base_url)


def mark_turn_failed(turn_id: str, error: dict[str, Any], base_url: Optional[str] = None) -> dict[str, Any]:
    return update_turn_status(turn_id, "failed", error=error, base_url=base_url)


def update_turn_status(
    turn_id: str,
    status: str,
    result: Optional[dict[str, Any]] = None,
    error: Optional[dict[str, Any]] = None,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    base = (base_url or BASE_URL).rstrip("/")
    conn = get_db()
    try:
        ensure_queued_turns_table(conn)
        existing = conn.execute("SELECT turn_id FROM queued_turns WHERE turn_id = ?", (turn_id,)).fetchone()
        if not existing:
            raise LookupError(f"turn_not_found:{turn_id}")
        assignments = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = [status]
        if status == "processing":
            assignments.append("processing_started_at = COALESCE(processing_started_at, CURRENT_TIMESTAMP)")
        if status in TERMINAL_STATUSES:
            assignments.append("completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)")
        if result is not None:
            assignments.append("result_json = ?")
            params.append(json.dumps(result))
        if error is not None:
            assignments.append("error_json = ?")
            params.append(json.dumps(error))
        params.append(turn_id)
        conn.execute(f"UPDATE queued_turns SET {', '.join(assignments)} WHERE turn_id = ?", tuple(params))
        conn.commit()
        row = _fetch_turn(conn, turn_id, base)
        return _row_to_status(row, base)
    finally:
        conn.close()
