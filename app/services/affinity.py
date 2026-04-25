"""
D20 Agent RPG — NPC Affinity Service.

Tracks per-NPC relationship affinity (0-100 scale) for each character.
Affinity influences:
  - NPC dialogue tone and information sharing
  - Shop discounts (70+ = 20% off, 90+ = 30% off)
  - Quest availability and NPC behavior (hostile/wary/neutral/friendly/devoted)

Affinity starts at 50 (neutral). Each interaction may adjust it via delta
returned by the DM agent (-20 to +15 typical range). The scale is clamped
0-100 and persisted in character_npc_interactions table.
"""

import json
from datetime import datetime
from typing import Optional, Dict, List
from app.services.database import get_db


# ---------------------------------------------------------------------------
# Affinity thresholds and discounts
# ---------------------------------------------------------------------------

AFFINITY_HOSTILE_MAX = 29   # 0-29: Hostile — refuses service, may attack
AFFINITY_WARY_MAX    = 49   # 30-49: Wary — curt dialogue, no discounts
AFFINITY_NEUTRAL_MAX = 69   # 50-69: Neutral — default behavior
AFFINITY_FRIENDLY_MIN = 70  # 70-89: Friendly — 20% discount, extra hints
AFFINITY_DEVOTED_MIN = 90   # 90-100: Devoted — 30% discount, rare items/secrets

DISCOUNT_FRIENDLY = 0.80  # 20% off
DISCOUNT_DEVOTED  = 0.70  # 30% off


# ---------------------------------------------------------------------------
# Core affinity operations
# ---------------------------------------------------------------------------

def get_affinity(character_id: str, npc_id: str) -> int:
    """
    Get current affinity score for a character/NPC pair.
    Returns 50 (neutral) if no interaction record exists yet.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT affinity FROM character_npc_interactions "
        "WHERE character_id = ? AND npc_id = ?",
        (character_id, npc_id)
    ).fetchone()
    conn.close()

    if row:
        return int(row["affinity"])
    return 50  # default neutral


def get_all_affinities(character_id: str) -> Dict[str, int]:
    """
    Get all NPC affinity scores for a character as {npc_id: affinity}.
    Only returns NPCs the character has interacted with at least once.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT npc_id, affinity FROM character_npc_interactions "
        "WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    conn.close()

    return {row["npc_id"]: int(row["affinity"]) for row in rows}


def update_affinity(character_id: str, npc_id: str, delta: int) -> int:
    """
    Adjust affinity by delta (can be positive or negative).
    Clamps to 0-100 range. Creates record if none exists.
    Returns the new affinity score.
    """
    conn = get_db()
    now = datetime.utcnow().isoformat()

    # Upsert: insert if not exists, otherwise update with clamped affinity
    current = get_affinity(character_id, npc_id)
    new_score = max(0, min(100, current + delta))

    # If record exists, UPDATE; else INSERT
    existing = conn.execute(
        "SELECT id FROM character_npc_interactions "
        "WHERE character_id = ? AND npc_id = ?",
        (character_id, npc_id)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE character_npc_interactions "
            "SET affinity = ?, last_interaction_at = ? "
            "WHERE character_id = ? AND npc_id = ?",
            (new_score, now, character_id, npc_id)
        )
    else:
        conn.execute(
            "INSERT INTO character_npc_interactions "
            "(character_id, npc_id, interaction_count, affinity, first_interaction_at, last_interaction_at) "
            "VALUES (?, ?, 1, ?, ?, ?)",
            (character_id, npc_id, new_score, now, now)
        )

    conn.commit()
    conn.close()
    return new_score


def get_discount_npcs(character_id: str) -> List[str]:
    """
    Get list of NPC IDs for whom the character qualifies for a shop discount
    (affinity >= 70). Used by trade handler to apply discounts.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT npc_id FROM character_npc_interactions "
        "WHERE character_id = ? AND affinity >= 70",
        (character_id,)
    ).fetchall()
    conn.close()

    return [row["npc_id"] for row in rows]


def calculate_discount(affinity: int) -> float:
    """
    Return discount multiplier for given affinity.
    70-89: 0.80 (20% off)
    90-100: 0.70 (30% off)
    <70: 1.00 (no discount)
    """
    if affinity >= 90:
        return DISCOUNT_DEVOTED
    if affinity >= 70:
        return DISCOUNT_FRIENDLY
    return 1.0


def get_affinity_status(affinity: int) -> str:
    """
    Return human-readable affinity status category.
    """
    if affinity <= AFFINITY_HOSTILE_MAX:
        return "hostile"
    if affinity <= AFFINITY_WARY_MAX:
        return "wary"
    if affinity <= AFFINITY_NEUTRAL_MAX:
        return "neutral"
    if affinity >= AFFINITY_DEVOTED_MIN:
        return "devoted"
    return "friendly"
