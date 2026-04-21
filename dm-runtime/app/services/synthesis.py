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
                    "text": d.get("text", ""),
                })

    return {
        "narration": {
            "scene": narration,
            "npc_lines": npc_lines,
            "tone": "neutral",
        },
        "mechanics": _extract_mechanics(server_result, world_ctx),
        "choices": _extract_choices(server_result, world_ctx),
        "server_trace": _extract_trace(server_result),
    }


def _extract_mechanics(server_result: dict, world_context: dict) -> dict:
    """Extract mechanical summary from server data."""
    char = world_context.get("character", {})
    return {
        "what_happened": server_result.get("dice_log", []),
        "hp": {
            "current": char.get("hp_current", 0),
            "max": char.get("hp_max", 0),
        },
        "location": world_context.get("location", {}).get("id", "unknown"),
    }


def _extract_choices(server_result: dict, world_context: dict) -> list:
    """Extract player choices from server data."""
    choices = []
    for conn in world_context.get("connections", []):
        choices.append({
            "id": conn.get("id", ""),
            "label": f"Go to {conn.get('name', conn.get('id', ''))}",
        })
    for ask in server_result.get("asks", []):
        choices.append({
            "id": ask.get("id", ""),
            "label": ask.get("label", ask.get("text", "")),
        })
    return choices


def _extract_trace(server_result: dict) -> dict:
    """Extract server trace for debugging."""
    return {
        "turn_id": server_result.get("turn_id"),
        "decision_point": server_result.get("decision_point"),
        "available_actions": server_result.get("available_actions", []),
    }
