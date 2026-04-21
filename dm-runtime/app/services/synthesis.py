"""DM synthesis — converts server payloads into narrated player-facing output.

The DM runtime NEVER validates rules. It only narrates from server-returned data.
world_context is the hard scope boundary — never invent NPCs, locations, or items not in it.

Priority:
1. LLM narration (Kimi Turbo via narrator module) — rich, immersive prose
2. Passthrough fallback — structured output when LLM unavailable
"""

from __future__ import annotations
import logging
from typing import Optional

from app.services.narrator import narrate as llm_narrate

logger = logging.getLogger(__name__)


async def synthesize_narration(server_result: dict, intent: dict, world_context: dict) -> dict:
    """Convert a server response into the final player-facing payload.

    Tries LLM narration first. Falls back to passthrough if LLM unavailable.
    """
    # Try LLM narration
    llm_output = await llm_narrate(server_result, intent, world_context)

    if llm_output and llm_output.get("scene"):
        return _build_from_llm(llm_output, server_result, world_context)
    else:
        return _build_passthrough(server_result, intent, world_context)


def _build_from_llm(llm_output: dict, server_result: dict, world_context: dict) -> dict:
    """Build response using LLM narration."""
    # NPC lines from LLM
    npc_lines = []
    for line in llm_output.get("npc_lines", []):
        if isinstance(line, dict) and line.get("speaker") and line.get("text"):
            npc_lines.append({
                "speaker": line["speaker"],
                "text": line["text"],
                "tone": line.get("tone"),
            })

    # Choices from server context (LLM doesn't invent choices)
    choices = _extract_choices(server_result, world_context)

    return {
        "narration": {
            "scene": llm_output["scene"],
            "npc_lines": npc_lines,
            "tone": llm_output.get("tone", "neutral"),
        },
        "mechanics": _extract_mechanics(server_result, world_context),
        "choices": choices,
        "server_trace": _extract_trace(server_result),
    }


def _build_passthrough(server_result: dict, intent: dict, world_context: dict) -> dict:
    """Fallback: structured passthrough when LLM is unavailable."""
    narration = server_result.get("narration", "")
    world_ctx = server_result.get("world_context", world_context)

    # Extract NPC lines from world context
    npc_lines = []
    for npc in world_ctx.get("npcs", []):
        if npc.get("dialogue"):
            for d in npc["dialogue"][:1]:  # first available line
                npc_lines.append({
                    "speaker": npc.get("name", "Unknown"),
                    "text": d.get("text") or d.get("template", ""),
                })

    mechanics = _extract_mechanics(server_result, world_ctx)

    return {
        "narration": {
            "scene": narration,
            "npc_lines": npc_lines,
            "tone": "neutral",
        },
        "mechanics": mechanics,
        "choices": _extract_choices(server_result, world_ctx),
        "server_trace": _extract_trace(server_result),
    }


def _extract_mechanics(server_result: dict, world_context: dict) -> dict:
    """Extract mechanical summary from server data.

    MechanicsPayload.what_happened requires a list[str], so this function must
    normalize richer server structures (dice/event dicts) into readable strings.
    """
    char = world_context.get("character") or server_result.get("character_state", {})

    what_happened = []

    for event in server_result.get("events", []):
        if isinstance(event, dict):
            desc = event.get("desc") or event.get("description") or event.get("event")
            if desc:
                what_happened.append(str(desc))
        elif event:
            what_happened.append(str(event))

    for entry in server_result.get("dice_log", []):
        if isinstance(entry, dict):
            context = entry.get("context", "Action")
            if entry.get("type") == "d20":
                raw = entry.get("raw")
                total = entry.get("total")
                if raw is not None and total is not None:
                    what_happened.append(f"{context}: rolled {raw} (total {total})")
                else:
                    what_happened.append(str(context))
            elif entry.get("type") == "choice":
                chosen = entry.get("chosen") or entry.get("decision")
                if chosen:
                    what_happened.append(f"{context}: chose {chosen}")
                else:
                    what_happened.append(str(context))
            else:
                what_happened.append(str(context))
        elif entry:
            what_happened.append(str(entry))

    # Normalize HP from multiple server response shapes:
    # - actions endpoint: character_state = {"hp": {"current": X, "max": Y}, ...}
    # - turn/start endpoint: hp_end, hp_max at top level
    # - world_context: character = {"hp_current": X, "hp_max": Y, ...}
    hp_current = 0
    hp_max = 0
    if isinstance(char.get("hp"), dict):
        hp_current = char["hp"].get("current", 0)
        hp_max = char["hp"].get("max", 0)
    elif "hp_current" in char:
        hp_current = char.get("hp_current", 0)
        hp_max = char.get("hp_max", 0)
    if not hp_current and not hp_max:
        hp_current = server_result.get("hp_end", 0)
        hp_max = server_result.get("hp_max", 0)

    mechanics = {
        "what_happened": what_happened,
        "hp": {
            "current": hp_current,
            "max": hp_max,
        },
        "location": world_context.get("location", {}).get("id") or server_result.get("current_location") or char.get("location_id", "unknown"),
    }

    xp_end = server_result.get("xp_end")
    xp_start = server_result.get("xp_start")
    if xp_end is not None:
        mechanics["xp"] = {
            "current": xp_end,
            "gained": max(0, xp_end - (xp_start or 0)),
        }

    loot = server_result.get("loot")
    if loot:
        mechanics["loot"] = loot

    return mechanics


def _extract_choices(server_result: dict, world_context: dict) -> list:
    """Extract player choices from server data."""
    choices = []
    for conn in world_context.get("connections", []):
        choices.append({
            "id": conn.get("id", ""),
            "label": f"Go to {conn.get('name', conn.get('id', ''))}",
            "description": conn.get("description"),
        })

    for ask in server_result.get("asks", []):
        if ask.get("options"):
            for option in ask.get("options", []):
                choices.append({
                    "id": str(option),
                    "label": str(option).replace("_", " ").title(),
                    "description": ask.get("description"),
                })
        else:
            label = ask.get("label") or ask.get("text") or ask.get("description") or ask.get("type", "Continue")
            choices.append({
                "id": ask.get("id") or ask.get("type") or str(label).lower().replace(" ", "_"),
                "label": label,
                "description": ask.get("description"),
            })
    return choices


def _extract_trace(server_result: dict) -> dict:
    """Extract server trace for debugging."""
    return {
        "turn_id": server_result.get("turn_id"),
        "decision_point": server_result.get("decision_point"),
        "available_actions": server_result.get("available_actions", []),
    }
