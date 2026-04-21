"""DM Narrator — LLM-powered narration via Kimi Turbo.

Uses OpenAI-compatible API (Fire Pass or direct Kimi endpoint) to generate
rich DM prose from server payloads. Enforces world_context scope boundary:
the LLM may only reference NPCs, locations, items, and events present in
the server-provided context.

Fallback: if LLM is unavailable, returns passthrough narration.
"""

from __future__ import annotations
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Configuration ---
# Supports Fire Pass proxy or direct Kimi/OpenAI-compatible endpoints
NARRATOR_API_KEY = os.environ.get("DM_FIRE_PASS_API_KEY", "") or os.environ.get("KIMI_API_KEY", "")
NARRATOR_BASE_URL = os.environ.get("DM_FIRE_PASS_BASE_URL", "https://api.moonshot.cn/v1")
NARRATOR_MODEL = os.environ.get("DM_NARRATOR_MODEL", "kimi-turbo")
NARRATOR_ENABLED = os.environ.get("DM_NARRATOR_ENABLED", "true").lower() == "true"
NARRATOR_TIMEOUT = int(os.environ.get("DM_NARRATOR_TIMEOUT", "30"))
NARRATOR_MAX_TOKENS = int(os.environ.get("DM_NARRATOR_MAX_TOKENS", "800"))

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

    # Player's intent
    intent_desc = intent.get("details", {}).get("intent", intent.get("action_type", "unknown"))
    parts.append(f"PLAYER INTENT: {intent_desc}")

    # Quest context
    quests = world_context.get("active_quests", [])
    if quests:
        q_desc = [f"- {q.get('name', '?')}: {q.get('status', '?')}" for q in quests[:3]]
        parts.append("ACTIVE QUESTS:\n" + "\n".join(q_desc))

    # Front progression
    front = world_context.get("front_progression", {})
    if front:
        parts.append(f"FRONT: {front.get('name', '?')} — Portent {front.get('current_portent', 0)}")

    return "\n\n".join(parts)


async def narrate(server_result: dict, intent: dict, world_context: dict) -> Optional[dict]:
    """Generate LLM-powered narration from server result.

    Returns dict with keys: scene, npc_lines, tone, choices_summary
    Returns None if LLM is unavailable (caller should use passthrough).
    """
    if not NARRATOR_ENABLED or not NARRATOR_API_KEY:
        logger.info("DM narrator disabled or no API key — using passthrough")
        return None

    try:
        import httpx

        context_prompt = _build_context_prompt(server_result, intent, world_context)

        messages = [
            {"role": "system", "content": DM_SYSTEM_PROMPT},
            {"role": "user", "content": context_prompt},
        ]

        async with httpx.AsyncClient(timeout=NARRATOR_TIMEOUT) as client:
            response = await client.post(
                f"{NARRATOR_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NARRATOR_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": NARRATOR_MODEL,
                    "messages": messages,
                    "max_tokens": NARRATOR_MAX_TOKENS,
                    "temperature": 0.8,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # Validate expected keys
            result = {
                "scene": parsed.get("scene", ""),
                "npc_lines": parsed.get("npc_lines", []),
                "tone": parsed.get("tone", "neutral"),
                "choices_summary": parsed.get("choices_summary", ""),
            }

            logger.info(f"DM narrator generated {len(result['scene'])} chars of prose")
            return result

    except json.JSONDecodeError as e:
        logger.warning(f"DM narrator returned invalid JSON: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"DM narrator API error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"DM narrator error: {e}")
        return None
