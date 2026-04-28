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
DM_SYSTEM_PROMPT = """You are the Dungeon Master for a 5E-compatible game called AgentDungeon.

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

    # NPCs present — use only available NPCs for DM speech; unavailable are context-only
    npcs_all = world_context.get("npcs", [])
    # Prefer explicit availability lists if provided by world_context
    available_npcs = world_context.get("npcs_available")
    if available_npcs is None:
        available_npcs = [n for n in npcs_all if n.get("available", True)]
    if available_npcs:
        npc_desc = []
        for npc in available_npcs[:5]:
            name = npc.get("name", "Unknown")
            personality = npc.get("personality", "")
            dialogue = npc.get("dialogue", [])
            d_text = dialogue[0].get("text", "") if dialogue else ""
            npc_desc.append(f"- {name}: {personality}" + (f' (says: "{d_text}")' if d_text else ""))
        parts.append("NPCs PRESENT:\n" + "\n".join(npc_desc))

    # Include unavailable NPCs as context (not speakable)
    unavailable_npcs = world_context.get("npcs_unavailable")
    if unavailable_npcs is None:
        unavailable_npcs = [n for n in npcs_all if not n.get("available", True)]
    if unavailable_npcs:
        unavail_lines = []
        for npc in unavailable_npcs[:5]:
            name = npc.get("name", "Unknown")
            reason = npc.get("unavailability_reason", "Not available")
            unavail_lines.append(f"- {name}: {reason}")
        parts.append("OTHER NPCS (unavailable):\n" + "\n".join(unavail_lines))

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

    # Narrative flags — story progression markers
    narrative_flags = world_context.get("narrative_flags", {})
    if narrative_flags:
        flag_lines = [f"- {k}: {v}" for k, v in list(narrative_flags.items())[:10]]
        parts.append("NARRATIVE FLAGS:\n" + "\n".join(flag_lines))

    # Key items — critical story items in inventory
    key_items = world_context.get("key_items", [])
    if key_items:
        ki_lines = []
        for ki in key_items[:5]:
            name = ki.get("name", ki.get("id", "?"))
            desc = ki.get("description", "")[:80].replace("\n", " ")
            ki_lines.append(f"- {name}: {desc}")
        parts.append("KEY ITEMS:\n" + "\n".join(ki_lines))


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
            parts.append("EXPLORATION LOOT HISTORY:\n" + "\n".join(loot_lines))

        # Hub social — cross-NPC rumors/reactions
        hub_social = social.get("hub_social", {})
        if hub_social:
            hub_rumors = hub_social.get("rumors", [])
            if hub_rumors:
                rumor_lines = []
                for r in hub_rumors[:5]:
                    key = r.get('key', '?')
                    sentiment = r.get('sentiment', 0)
                    spread = r.get('spread', 0)
                    rumor_lines.append(f"- {key}: sentiment={sentiment} spread={spread}")
                parts.append("HUB RUMORS (cross-NPC awareness):\n" + "\n".join(rumor_lines))
            summary = hub_social.get("summary_text", "")
            if summary:
                parts.append(f"HUB ATMOSPHERE: {summary}")

    return "\n\n".join(parts)


def _validate_scope(llm_output: dict, world_context: dict) -> bool:
    """Validate that LLM output stays within the world_context scope boundary.

    Checks enforced (scope):
    1. NPC speakers must exist in world_context npcs[]
    2. Scene location mentions must align with world_context (current location or connections)
    3. Scene must not reference key_items not present in world_context key_items[]
    4. Narrated outcomes must be consistent with server_result (death, quest completion)

    Returns True if all checks pass (or are skipped due to insufficient context data).
    """
    allowed_npcs = {n.get("name", "").lower() for n in world_context.get("npcs", []) if n.get("name")}

    def potential_entities(text: str):
        """Extract candidate proper-noun tokens from scene, filtering obvious pronouns."""
        # Accept 2+ consecutive TitleCase words; skip common stop list words
        COMMON = {"i", "you", "your", "yours", "someone", "something", "nothing",
                  "anyone", "anybody", "everyone", "everybody", "nobody",
                  "the", "a", "an", "my", "our", "their", "his", "her", "its",
                  "this", "that", "these", "those", "all", "both", "each", "every",
                  "many", "few", "some", "such"}
        tokens = set(re.findall(r'(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)*', text))
        # Filter stop words and very short tokens (<4 chars unless multi-word)
        return {t for t in tokens if t.lower() not in COMMON and (len(t) >= 4 or ' ' in t)}

    # ── NPC speaker validation ─────────────────────────────────────────────
    for line in llm_output.get("npc_lines", []):
        speaker = line.get("speaker", "").lower().strip()
        if speaker and allowed_npcs and not any(
            speaker in an or an in speaker for an in allowed_npcs
        ):
            logger.warning(f"Scope violation: NPC speaker '{speaker}' not in world_context")
            return False

    # Precompute allowed_items (used by location+item checks)
    allowed_items = { (ki.get("name") or ki.get("id") or "").lower()
                     for ki in world_context.get("key_items", []) }

    # ── Location validation ─────────────────────────────────────────────────
    allowed_locations = {loc.get("name", "").lower() for loc in [world_context.get("location", {})] if loc.get("name")}
    for conn in world_context.get("connections", []):
        if isinstance(conn, dict):
            name = conn.get("name")
            if name:
                allowed_locations.add(name.lower())
        else:
            allowed_locations.add(str(conn).lower())

    scene = llm_output.get("scene", "")
    for token in potential_entities(scene):
        t = token.lower()
        # Skip if NPC, item, or already allowed location
        if t in allowed_npcs or t in allowed_items:
            continue
        if any(t in loc or loc in t for loc in allowed_locations):
            continue
        # Off-scope location — fail
        logger.warning(f"Off-scope location reference: '{token}' (allowed: {allowed_locations})")
        return False

    # ── Key item validation ──────────────────────────────────────────────────
    # If key_items exist in world, scene must not reference disallowed items
    if allowed_items:
        for token in potential_entities(scene):
            t = token.lower()
            if t in allowed_items or t in allowed_npcs:
                continue  # OK or handled elsewhere
            logger.warning(f"Off-scope item reference: '{token}'")
            return False

    # ── Outcome validation ───────────────────────────────────────────────────
    server_trace = world_context.get("server_trace", {})
    combat_log = server_trace.get("combat_log", [])
    active_quests = world_context.get("active_quests", [])

    scene_lower = scene.lower()

    # Death narration must have combat_log support
    death_phrases = {"dies", "death", "falls dead", "dead", "kills", "slays", "defeated", "killed"}
    if any(p in scene_lower for p in death_phrases):
        if not any(
            any(w in str(e).lower() for w in ("0 hp", "hp 0", "dead", "death"))
            for e in combat_log
        ):
            logger.warning("Death narration without combat evidence")
            return False

    # Quest completion narration must align with active quests
    complete_phrases = {"quest complete", "quest is complete", "quest completed",
                        "completed", "finished", "saved", "accomplished", "victory"}
    if any(p in scene_lower for p in complete_phrases):
        if not active_quests:
            logger.warning("Quest completion narration but active_quests is empty")
            return False
        for q in active_quests:
            if q.get("name", "").lower() in scene_lower:
                break  # OK: named matching active quest
        else:
            # No named quest — still OK (vague); optionally could require name
            pass

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
            # Preserve the Hermes session id even when prose is rejected. This
            # proves the actual DM agent ran while still refusing unsafe/off-scope
            # narration; synthesis will attach the session id to passthrough.
            if result.get("_hermes_session_id"):
                return {"_hermes_session_id": result["_hermes_session_id"], "_scope_rejected": True}
            return None

        logger.info(f"DM narrator generated {len(result['scene'])} chars of prose")
        return result

    except Exception as e:
        logger.warning(f"DM narrator error: {e}")
        return None
