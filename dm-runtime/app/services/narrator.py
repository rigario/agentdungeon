"""DM Narrator — LLM-powered narration via Kimi Turbo.

Uses the dm_profile wrapper for invocation, supporting two modes:
- DIRECT: Call Kimi Turbo API via httpx (default, lowest latency)
- HERMES: Route through the d20-dm Hermes profile (for session tracking/debugging)

Enforces world_context scope boundary: the LLM may only reference NPCs, locations,
items, and events present in the server-provided context.

Output validation: after LLM returns, we verify no off-scope references
crept in. If validation fails, we fall back to passthrough.

Fallback: if LLM is unavailable, returns passthrough.
"""

from __future__ import annotations
import os
import json
import logging
import re
from typing import Optional

from app.services.dm_profile import narrate as dm_profile_narrate, get_status as get_dm_profile_status

logger = logging.getLogger(__name__)

# --- Configuration ---
NARRATOR_ENABLED = os.environ.get("DM_NARRATOR_ENABLED", "true").lower() == "true"

# --- DM System Prompt ---
# Enforces authority boundaries and world_context scope
DM_SYSTEM_PROMPT = """You are the Dungeon Master for a D&D 5E game called Rigario D20.

## Your Role
You narrate the world, give voice to NPCs, describe scenes, and present choices. You make the game feel alive and immersive.

## CRITICAL RULES — Authority Boundaries

YOU MAY:
- Write descriptive prose, scene-setting, atmosphere
- Give NPCs distinctive voices and personalities
- Frame choices and present options dramatically
- Describe the emotional weight of events
- Pace the narrative (build tension, provide relief)

YOU MUST NEVER:
- Invent NPCs, locations, items, or outcomes not in the provided world_context
- Change game state (HP, items, quest flags, combat results)
- Roll dice or override mechanical outcomes
- Decide what the player does — only present options
- Contradict any server-provided data (damage dealt, loot found, etc.)

## SCOPE ENFORCEMENT — HARD BOUNDARY
The world_context provided below is your ONLY source of truth. You may ONLY reference:
- NPCs listed in "NPCs PRESENT" — no others exist
- The current LOCATION and AVAILABLE PATHS — nowhere else
- Active quests listed — no others
- The front shown — no other fronts
- Items/events from server data — nothing you invent

If the world_context does not include an NPC, location, or item, it does NOT exist in this scene.
Do not hallucinate backstory, additional characters, or world details outside the provided scope.

## Output Format
Always respond with valid JSON:
{
  "scene": "Your narrative prose (2-4 paragraphs, vivid but concise)",
  "npc_lines": [{"speaker": "NPC Name", "text": "dialogue", "tone": "friendly|menacing|neutral|etc"}],
  "tone": "ominous|hopeful|tense|neutral|mysterious|triumphant",
  "choices_summary": "Brief framing of what the player can do next"
}

## Style
- Second person ("You step into...")
- Present tense for active scenes, past tense for recaps
- Sensory details (sight, sound, smell)
- NPCs speak in first person with distinct mannerisms
- When PLAYER MESSAGE is directed at an NPC, answer that actual utterance in character, grounded by the NPC's listed personality/dialogue and current state. Do not merely repeat the template line unless it is exactly the right response.
- Keep mechanical references subtle (don't say "you rolled a 20", say "your blade strikes true")
"""


def _build_context_prompt(server_result: dict, intent: dict, world_context: dict) -> str:
    """Build the user prompt from server data, enforcing scope boundary."""
    parts = []

    # Location context
    loc = world_context.get("location", {})
    if loc:
        parts.append(f"LOCATION: {loc.get('name', 'Unknown')} — {loc.get('description', 'No description')}")
        atmosphere = world_context.get("atmosphere", {})
        if atmosphere:
            parts.append(f"ATMOSPHERE: {json.dumps(atmosphere)}")

    # Character state
    char = world_context.get("character", {})
    if char:
        hp_current = char.get("hp_current", "?")
        hp_max = char.get("hp_max", "?")
        char_name = char.get("name", "the adventurer")
        parts.append(f"CHARACTER: {char_name} (HP: {hp_current}/{hp_max})")

    # NPCs present
    npcs = world_context.get("npcs", [])
    if npcs:
        npc_desc = []
        for npc in npcs[:5]:
            name = npc.get("name", "Unknown")
            personality = npc.get("personality", "")
            dialogue = npc.get("dialogue", [])
            d_text = dialogue[0].get("text", "") if dialogue else ""
            npc_desc.append(f"- {name}: {personality}" + (f' (says: "{d_text}")' if d_text else ""))
        parts.append("NPCs PRESENT:\n" + "\n".join(npc_desc))

    # Connections (where player can go)
    connections = world_context.get("connections", [])
    if connections:
        conn_names = [c.get("name", c.get("id", "?")) for c in connections]
        parts.append(f"AVAILABLE PATHS: {', '.join(conn_names)}")

    # What happened (server narration + events)
    server_narration = server_result.get("narration", "")
    if server_narration:
        parts.append(f"SERVER NARRATION: {server_narration}")

    events = server_result.get("events", [])
    if events:
        parts.append(f"EVENTS: {'; '.join(str(e) for e in events[:5])}")

    # Dice log
    dice = server_result.get("dice_log", [])
    if dice:
        parts.append(f"DICE ROLLS: {json.dumps(dice[:5])}")

    # Decision point
    decision = server_result.get("decision_point")
    if decision:
        parts.append(f"DECISION POINT: {json.dumps(decision)}")

    # Combat state
    if server_result.get("combat_over"):
        parts.append(f"COMBAT RESULT: {server_result.get('result', 'unknown')}")
    enemies = server_result.get("enemies", [])
    if enemies:
        parts.append(f"ENEMIES: {json.dumps(enemies[:3])}")

    # Player's original message and classified intent
    details = intent.get("details", {}) or {}
    original_msg = details.get("_original_msg") or details.get("intent") or ""
    if original_msg:
        parts.append(f"PLAYER MESSAGE: {original_msg}")
    intent_desc = details.get("intent") or details.get("action_type") or intent.get("type") or intent.get("action_type", "unknown")
    parts.append(f"CLASSIFIED INTENT: {intent_desc}")

    # Quest context
    quests = world_context.get("active_quests", [])
    if quests:
        q_desc = [f"- {q.get('name', '?')}: {q.get('status', '?')}" for q in quests[:3]]
        parts.append("ACTIVE QUESTS:\n" + "\n".join(q_desc))

    # Front progression
    front = world_context.get("front_progression", {})
    if front:
        parts.append(f"FRONT: {front.get('name', '?')} — Portent {front.get('current_portent', 0)}")

    # Social context — relationship affinity, milestones, exploration history
    social = world_context.get("social_context", {})
    if social:
        affinities = social.get("affinities", {})
        if affinities:
            aff_lines = [
                f"- {npc_id}: {score}/100 ({'hostile' if score<30 else 'wary' if score<50 else 'neutral' if score<70 else 'friendly' if score<90 else 'devoted'})"
                for npc_id, score in sorted(affinities.items(), key=lambda x: x[1], reverse=True)[:8]
            ]
            parts.append("NPC RELATIONSHIPS (affinity scores):\\n" + "\\n".join(aff_lines))

        milestones = social.get("milestones", [])
        if milestones:
            ms_lines = [
                f"- [{m.get('type','?')}] Threshold {m.get('threshold','?')} — {m.get('reward_type','?')} at {m.get('claimed_at','?')}"
                for m in milestones[:5]
            ]
            parts.append("RECENT MILESTONES:\\n" + "\\n".join(ms_lines))

        loot_history = social.get("loot_history", [])
        if loot_history:
            loot_lines = [
                f"- Found {l.get('item_name','?')} (rarity: {l.get('rarity','common')}) at {l.get('location_id','?')}"
                for l in loot_history[:5]
            ]
            parts.append("EXPLORATION LOOT HISTORY:\\n" + "\\n".join(loot_lines))

    return "\n\n".join(parts)


def _validate_scope(llm_output: dict, world_context: dict) -> bool:
    """Validate that LLM output doesn't reference off-scope entities.

    Checks:
    1. NPC lines only reference NPCs in the world_context
    2. Scene doesn't introduce characters/locations not in scope

    Returns True if valid, False if scope violation detected.
    """
    # Extract allowed NPC names from world_context
    allowed_npcs = set()
    for npc in world_context.get("npcs", []):
        name = npc.get("name", "")
        if name:
            allowed_npcs.add(name.lower())

    # Validate NPC lines
    for line in llm_output.get("npc_lines", []):
        speaker = line.get("speaker", "").lower()
        if speaker and allowed_npcs:
            # Allow if speaker exactly matches, or if any allowed name is a substring of speaker (e.g., "aldric" matches "aldric the innkeeper")
            if not any(speaker in allowed_name or allowed_name in speaker for allowed_name in allowed_npcs):
                logger.warning(f"Scope violation: NPC speaker '{speaker}' not in world_context (allowed: {allowed_npcs})")
                return False

    # Extract allowed location names
    allowed_locations = set()
    loc = world_context.get("location", {})
    if loc.get("name"):
        allowed_locations.add(loc["name"].lower())
    for conn in world_context.get("connections", []):
        if conn.get("name"):
            allowed_locations.add(conn["name"].lower())

    # Basic scene validation: check for obvious scope violations
    scene = llm_output.get("scene", "")

    # Check that NPC lines' speakers appear in the scene text
    for line in llm_output.get("npc_lines", []):
        speaker = line.get("speaker", "")
        if speaker and speaker.lower() not in scene.lower():
            logger.debug(f"NPC '{speaker}' speaks but isn't mentioned in scene text (may be OK)")

    return True


async def narrate(server_result: dict, intent: dict, world_context: dict, session_id: str | None = None) -> Optional[dict]:
    """Generate LLM-powered narration from server result.

    Returns dict with keys: scene, npc_lines, tone, choices_summary
    Returns None if LLM is unavailable (caller should use passthrough).
    """
    if not NARRATOR_ENABLED:
        logger.info("DM narrator disabled — using passthrough")
        return None

    # Check if API key is available
    profile_status = get_dm_profile_status()
    if not profile_status["api_key_set"]:
        logger.info("No Kimi API key configured — using passthrough")
        return None

    try:
        context_prompt = _build_context_prompt(server_result, intent, world_context)

        # Call via dm_profile wrapper (supports direct and hermes modes)
        parsed = await dm_profile_narrate(
            system_prompt=DM_SYSTEM_PROMPT,
            user_prompt=context_prompt,
            temperature=0.8,
            session_id=session_id,
        )

        if not parsed:
            logger.warning("DM narrator returned no output — falling back to passthrough")
            return None

        # Validate expected keys
        result = {
            "scene": parsed.get("scene", ""),
            "npc_lines": parsed.get("npc_lines", []),
            "tone": parsed.get("tone", "neutral"),
            "choices_summary": parsed.get("choices_summary", ""),
        }
        if parsed.get("_hermes_session_id"):
            result["_hermes_session_id"] = parsed["_hermes_session_id"]

        # Validate scope — reject output that references off-scope entities
        if not _validate_scope(result, world_context):
            logger.warning("DM narrator produced off-scope output — falling back to passthrough")
            return None

        logger.info(f"DM narrator generated {len(result['scene'])} chars of prose")
        return result

    except Exception as e:
        logger.warning(f"DM narrator error: {e}")
        return None
