"""Campaign management helpers.

Provides:
- get_campaign(campaign_id): fetch campaign metadata
- get_character_campaign(character_id): return campaign_id for a character
- get_campaign_locations/encounters/npcs(campaign_id): world content per campaign
"""

from app.services.database import get_db
from typing import Optional, Dict, Any, List


def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM campaigns WHERE id = ? AND is_active = 1",
        (campaign_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_character_campaign(character_id: str) -> Optional[str]:
    conn = get_db()
    row = conn.execute(
        "SELECT campaign_id FROM characters WHERE id = ?",
        (character_id,)
    ).fetchone()
    conn.close()
    return row['campaign_id'] if row else None


def get_campaign_locations(campaign_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM locations WHERE campaign_id = ?",
        (campaign_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campaign_encounters(campaign_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM encounters WHERE campaign_id = ?",
        (campaign_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campaign_npcs(campaign_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM npcs WHERE campaign_id = ?",
        (campaign_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def validate_character_campaign_access(character_id: str, campaign_id: str) -> bool:
    """Ensure character belongs to the requested campaign."""
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM characters WHERE id = ? AND campaign_id = ?",
        (character_id, campaign_id)
    ).fetchone()
    conn.close()
    return row is not None

def get_campaign_from_character(character_id: str) -> Optional[Dict[str, Any]]:
    """Return the full campaign record for a character's campaign."""
    cid = get_character_campaign(character_id)
    if cid:
        return get_campaign(cid)
    return None


def list_campaigns() -> list[Dict[str, Any]]:
    """List all active campaigns."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM campaigns WHERE is_active = 1 ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_campaign(campaign_id: str, name: str, description: str = "") -> Dict[str, Any]:
    """Create a new campaign."""
    conn = get_db()
    conn.execute(
        "INSERT INTO campaigns (id, name, description) VALUES (?, ?, ?)",
        (campaign_id, name, description)
    )
    conn.commit()
    conn.close()
    return {"id": campaign_id, "name": name, "description": description}

