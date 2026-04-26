"""
D20 Agent RPG — Hub Rumor Service.

Tracks hub-level social state that compounds across NPC interactions.
When a player interacts with an NPC, important dialogue outcomes generate
"rumors" that other NPCs in the same hub can become aware of and react to.

Rumor keys (canonical):
  aldric_confessed                — Aldric admitted lying about Hollow Eye
  marta_gw_warning                — Marta warned about Green Woman dangers
  ser_maren_trust_shift           — Ser Maren's trust in player changed
  kol_backstory_known             — Player learned Brother Kol's history

Sentiment scale: -1 (negative/distrust), 0 (neutral), 1 (positive/trust)
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from app.services.database import get_db

# ---------------------------------------------------------------------------
# Sentiment constants
# ---------------------------------------------------------------------------
SENTIMENT_NEGATIVE = -1
SENTIMENT_NEUTRAL = 0
SENTIMENT_POSITIVE = 1

# ---------------------------------------------------------------------------
# Canonical rumor keys — align with narrative flags / dialogue outcomes
# ---------------------------------------------------------------------------
RUMOR_ALDRIC_CONFESSED = 'aldric_confessed'
RUMOR_MARTA_GW_WARNING = 'marta_gw_warning'
RUMOR_SER_MAREN_TRUST = 'ser_maren_trust_shift'
RUMOR_KOL_BACKSTORY = 'kol_backstory_known'

# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def record_rumor(
    character_id: str,
    location_id: str,
    rumor_key: str,
    sentiment: int,
    source_npc_id: Optional[str] = None,
) -> bool:
    """
    Record or update a hub rumor.
    
    Idempotent: if the rumor already exists for this (character, location, key),
    we update last_seen_at, increment spread_count, and update sentiment if
    the new sentiment is stronger (positive reinforces, negative compounds).
    
    Returns True if this is a new rumor record, False if it was an update.
    """
    now = datetime.utcnow().isoformat()
    conn = get_db()
    
    try:
        existing = conn.execute(
            "SELECT id, sentiment, spread_count FROM hub_rumors "
            "WHERE character_id = ? AND location_id = ? AND rumor_key = ?",
            (character_id, location_id, rumor_key)
        ).fetchone()
        
        if existing:
            # Update: choose sentiment by taking the most "intense" value
            # (abs(sentiment) larger wins; if equal, positive wins)
            old_sentiment = existing['sentiment']
            new_sentiment = old_sentiment
            if abs(sentiment) > abs(old_sentiment):
                new_sentiment = sentiment
            elif abs(sentiment) == abs(old_sentiment) and sentiment > old_sentiment:
                new_sentiment = sentiment
            
            conn.execute(
                "UPDATE hub_rumors "
                "SET sentiment = ?, last_seen_at = ?, spread_count = spread_count + 1 "
                "WHERE id = ?",
                (new_sentiment, now, existing['id'])
            )
            conn.commit()
            return False
        else:
            # Insert new rumor
            conn.execute(
                "INSERT INTO hub_rumors "
                "(character_id, location_id, rumor_key, sentiment, source_npc_id, first_seen_at, last_seen_at, spread_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (character_id, location_id, rumor_key, sentiment, source_npc_id, now, now)
            )
            conn.commit()
            return True
    finally:
        conn.close()


def get_hub_rumors(character_id: str, location_id: str) -> List[Dict[str, Any]]:
    """
    Return all active hub rumors for a character at a location,
    sorted by last_seen_at descending (most recent first).
    
    Each rumor: {rumor_key, sentiment, source_npc_id, spread_count, last_seen_at}
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT rumor_key, sentiment, source_npc_id, spread_count, last_seen_at "
        "FROM hub_rumors "
        "WHERE character_id = ? AND location_id = ? "
        "ORDER BY last_seen_at DESC",
        (character_id, location_id)
    ).fetchall()
    conn.close()
    
    return [dict(r) for r in rows]


def get_hub_social_state(character_id: str, location_id: str) -> Dict[str, Any]:
    """
    Build a concise hub social state summary for DM context.
    
    Returns a lightweight dict designed for token-efficient inclusion in
    world_context:
    {
        'rumors': [
            {'key': 'aldric_confessed', 'sentiment': 1, 'spread': 2},
            ...
        ],
        'summary_text': "Short 1-2 sentence summary of key tensions"
    }
    """
    rumors = get_hub_rumors(character_id, location_id)
    
    if not rumors:
        return {'rumors': [], 'summary_text': ''}
    
    # Build a natural-language summary (1-2 sentences)
    summary_parts = []
    positive = [r for r in rumors if r['sentiment'] > 0]
    negative = [r for r in rumors if r['sentiment'] < 0]
    
    if positive:
        keys = [r['rumor_key'].replace('_', ' ') for r in positive[:2]]
        summary_parts.append(f"Locals speak well of: {', '.join(keys)}.")
    if negative:
        keys = [r['rumor_key'].replace('_', ' ') for r in negative[:2]]
        summary_parts.append(f"Tensions noted: {', '.join(keys)}.")
    
    summary = ' '.join(summary_parts)
    
    return {
        'rumors': [
            {'key': r['rumor_key'], 'sentiment': r['sentiment'], 'spread': r['spread_count']}
            for r in rumors
        ],
        'summary_text': summary,
    }


def get_reaction_modifiers(character_id: str, location_id: str, npc_id: str) -> Dict[str, Any]:
    """
    Return rumor-based reaction modifiers for a specific NPC.
    
    This function encapsulates cross-NPC reaction logic. Other NPCs can
    be influenced by rumors about what the player did with other locals.
    
    Returns a dict with:
      - affinity_bonus: int (additive to affinity delta on next interaction)
      - dialogue_hint: str (optional template hint for DM)
      - tone_modifier: str ('warmer', 'colder', 'neutral')
    """
    rumors = get_hub_rumors(character_id, location_id)
    modifiers = {'affinity_bonus': 0, 'dialogue_hint': None, 'tone_modifier': 'neutral'}
    
    # Reaction: NPC learns player helped Aldric confess → warmer tone
    if any(r['rumor_key'] == RUMOR_ALDRIC_CONFESSED for r in rumors):
        if npc_id in ['npc-marta', 'npc-ser-maren']:
            modifiers['affinity_bonus'] = 5
            modifiers['dialogue_hint'] = 'aldric_confession_known'
            modifiers['tone_modifier'] = 'warmer'
    
    # Reaction: NPC learns player heard Marta's Green Woman warning → trust
    if any(r['rumor_key'] == RUMOR_MARTA_GW_WARNING for r in rumors):
        if npc_id == 'npc-green-woman':
            modifiers['affinity_bonus'] = 3
            modifiers['dialogue_hint'] = 'marta_warning_received'
            modifiers['tone_modifier'] = 'cautious_but_grateful'
    
    # Reaction: Ser Maren trusts player more after cross-verification
    if any(r['rumor_key'] == RUMOR_ALDRIC_CONFESSED for r in rumors):
        if npc_id == 'npc-ser-maren':
            modifiers['affinity_bonus'] = 8  # Maren values truth
            modifiers['dialogue_hint'] = 'maren_truth_appreciated'
            modifiers['tone_modifier'] = 'respectful'

    # Reaction: Ser Maren values Marta's intel on Hollow Eye
    if any(r['rumor_key'] == 'marta_hollow_eye_grudge' for r in rumors):
        if npc_id == 'npc-ser-maren':
            modifiers['affinity_bonus'] = 5
            modifiers['dialogue_hint'] = 'marta_grudge_known'
            modifiers['tone_modifier'] = 'respectful'
    
    return modifiers


def clear_hub_rumors(character_id: str, location_id: str) -> int:
    """
    Expire/delete all rumors for a character at a location.
    Used when leaving a hub (optional, not required for MVP).
    
    Returns count of deleted rows.
    """
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM hub_rumors WHERE character_id = ? AND location_id = ?",
        (character_id, location_id)
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
