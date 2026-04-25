"""
D20 Agent RPG — NPC Interaction Milestone Tracking.

Milestone thresholds:
  3 unique NPCs  → hint about Hollow Eye
  5 unique NPCs  → Adventurer's Pack (rope, torch, rations)
  7 unique NPCs  → Enchanted Amulet (+1 AC)
  9 unique NPCs  → Key clue: "The seal is weakening"
"""

import json
from datetime import datetime
from app.services.database import get_db


# ---------------------------------------------------------------------------
# Milestone definitions
# ---------------------------------------------------------------------------

MILESTONE_THRESHOLDS = [
    # (unique_npc_count, reward_type, reward_data_json)
    (3,  "hint",   json.dumps({"text": "Strange-eyed watchers in the crowd seem interested in you. Keep your head down."})),
    (5,  "item",   json.dumps({"item_id": "adventurers_pack", "quantity": 1})),
    (7,  "item",   json.dumps({"item_id": "enchanted_amulet", "quantity": 1})),
    (9,  "flag",   json.dumps({"flag": "seal_weakening_clue", "value": "1"})),
]

# Human-readable item names for DM narration / UI
ITEM_DISPLAY_NAMES = {
    "adventurers_pack":  "Adventurer's Pack",
    "enchanted_amulet":  "Enchanted Amulet (+1 AC)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_npc_milestones(character_id: str):
    """
    Check whether the character has reached any new milestone thresholds
    based on distinct NPC interaction counts.

    Returns a list of newly-claimed milestone dicts that were NOT previously
    recorded. Each dict: {milestone_type, threshold, reward_type, reward_data}

    Side effect: newly-claimed milestones are INSERTed into
    character_milestones; claimed_at = datetime.utcnow().isoformat().
    Duplicate claims prevented by UNIQUE(character_id, milestone_type, threshold).
    """
    conn = get_db()

    # Count distinct NPCs this character has interacted with
    row = conn.execute("""
        SELECT COUNT(DISTINCT npc_id) as cnt
          FROM character_npc_interactions
         WHERE character_id = ?
    """, (character_id,)).fetchone()
    npc_count = row["cnt"] if row else 0

    newly_claimed = []
    now_iso = datetime.utcnow().isoformat()

    for threshold, reward_type, reward_data_json in MILESTONE_THRESHOLDS:
        if npc_count >= threshold:
            try:
                conn.execute("""
                    INSERT INTO character_milestones
                        (character_id, milestone_type, threshold,
                         claimed_at, reward_type, reward_data)
                    VALUES (?, 'npc_count', ?, ?, ?, ?)
                """, (character_id, threshold, now_iso, reward_type, reward_data_json))
                claimed = {
                    "milestone_type": "npc_count",
                    "threshold":       threshold,
                    "reward_type":     reward_type,
                    "reward_data":     json.loads(reward_data_json),
                }
                newly_claimed.append(claimed)
            except Exception:
                # UNIQUE constraint — milestone already claimed
                pass

    conn.commit()
    conn.close()

    return newly_claimed


def get_milestone_summary(character_id: str):
    """
    Return the character's milestone summary:
    {
      "npc_interactions_count": <int>,
      "milestones_claimed":      [ {milestone_type, threshold, ...}, ... ]
    }
    Used by DM context builder and portal views.
    """
    conn = get_db()

    # Already-claimed milestones
    rows = conn.execute("""
        SELECT milestone_type, threshold, claimed_at, reward_type, reward_data
          FROM character_milestones
         WHERE character_id = ?
         ORDER BY threshold
    """, (character_id,)).fetchall()

    claimed = []
    for r in rows:
        claimed.append({
            "milestone_type": r["milestone_type"],
            "threshold":      r["threshold"],
            "claimed_at":     r["claimed_at"],
            "reward_type":    r["reward_type"],
            "reward_data":    json.loads(r["reward_data"]),
        })

    # Current distinct NPC count
    cnt_row = conn.execute("""
        SELECT COUNT(DISTINCT npc_id) as cnt
          FROM character_npc_interactions
         WHERE character_id = ?
    """, (character_id,)).fetchone()
    conn.close()

    return {
        "npc_interactions_count": cnt_row["cnt"] if cnt_row else 0,
        "milestones_claimed":     claimed,
    }
