"""DM synthesis — converts server payloads into narrated player-facing output.

The DM runtime NEVER validates rules. It only narrates from server-returned data.
world_context is the hard scope boundary — never invent NPCs, locations, or items not in it.
"""

from typing import Optional


# NOTE: classify_intent was removed — use app.services.intent_router.classify_intent instead.
# The turn router already imports from the correct module. This avoids duplicate logic.


def synthesize_narration(server_result: dict, intent: dict, world_context: dict) -> dict:
    """Convert a server response into the final player-facing payload.

    This is where DM personality, NPC voice, and scene description live.
    For now, this is a passthrough that structures the output.
    LLM-powered synthesis (Kimi 2.5 via Fire Pass) will replace this.
    """
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

    # Build choices from connections or asks
    choices = []
    for conn in world_ctx.get("connections", []):
        choices.append({
            "id": conn.get("id", ""),
            "label": f"Go to {conn.get('name', conn.get('id', ''))}",
        })
    for ask in server_result.get("asks", []):
        choices.append({
            "id": ask.get("id", ""),
            "label": ask.get("label", ask.get("text", "")),
        })

    return {
        "narration": {
            "scene": narration,
            "npc_lines": npc_lines,
            "tone": "neutral",
        },
        "mechanics": {
            "what_happened": server_result.get("dice_log", []),
            "hp": _extract_hp(world_ctx),
            "location": world_ctx.get("location", {}).get("id", "unknown"),
        },
        "choices": choices,
        "server_trace": {
            "turn_id": server_result.get("turn_id"),
            "decision_point": server_result.get("decision_point"),
            "available_actions": server_result.get("available_actions", []),
        },
    }


def _extract_hp(world_context: dict) -> dict:
    """Extract HP from world context if available."""
    char = world_context.get("character", {})
    return {
        "current": char.get("hp_current", 0),
        "max": char.get("hp_max", 0),
    }
