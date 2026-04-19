"""D20 Agent RPG — Event log endpoints."""

import json
from fastapi import APIRouter, HTTPException, Query
from app.services.database import get_db

router = APIRouter(prefix="/characters/{character_id}", tags=["events"])


@router.get("/event-log")
def get_event_log(character_id: str, since: str = Query(None, description="ISO timestamp filter")):
    """Get chronological event log for a character."""
    conn = get_db()

    # Verify character exists
    exists = conn.execute("SELECT 1 FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    if since:
        rows = conn.execute(
            """SELECT * FROM event_log WHERE character_id = ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (character_id, since)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM event_log WHERE character_id = ? ORDER BY timestamp ASC",
            (character_id,)
        ).fetchall()

    conn.close()

    events = []
    for row in rows:
        d = dict(row)
        if d.get("data_json"):
            d["data"] = json.loads(d["data_json"])
            del d["data_json"]
        else:
            d["data"] = {}
            d.pop("data_json", None)
        events.append(d)

    return {"character_id": character_id, "events": events}
