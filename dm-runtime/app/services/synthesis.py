"""DM synthesis — converts server payloads into narrated player-facing output.

The DM runtime NEVER validates rules. It only narrates from server-returned data.
world_context is the hard scope boundary — never invent NPCs, locations, or items not in it.
"""

from typing import Optional


def classify_intent(player_message: str) -> dict:
    """Classify player message into server-callable intent.

    Returns:
        {
            "type": "move" | "talk" | "combat" | "rest" | "explore" | "interact" | "puzzle" | "cast" | "general",
            "target": str | None,
            "details": dict,
            "server_endpoint": "actions" | "turn" | "combat"
        }
    """
    msg = player_message.lower().strip()

    # Movement intent
    move_keywords = ["go to", "travel to", "walk to", "head to", "move to", "visit", "enter", "return to"]
    for kw in move_keywords:
        if kw in msg:
            target = msg.split(kw)[-1].strip().split(".")[0].split(",")[0].strip()
            return {
                "type": "move",
                "target": target,
                "details": {"action_type": "move", "target": target},
                "server_endpoint": "actions",
            }

    # Rest intent
    rest_keywords = ["rest", "sleep", "camp", "recover", "long rest", "short rest"]
    if any(kw in msg for kw in rest_keywords):
        rest_type = "long" if "long" in msg else "short"
        return {
            "type": "rest",
            "target": None,
            "details": {"action_type": "rest", "details": {"rest_type": rest_type}},
            "server_endpoint": "actions",
        }

    # Combat intent
    combat_keywords = ["attack", "fight", "fight ", "hit", "strike", "cast", "use spell"]
    if any(kw in msg for kw in combat_keywords):
        return {
            "type": "combat",
            "target": None,
            "details": {"action_type": "attack"},
            "server_endpoint": "combat",
        }

    # Talk/interact intent
    talk_keywords = ["talk to", "speak to", "speak with", "ask", "tell", "say to", "chat with", "conversation"]
    if any(kw in msg for kw in talk_keywords):
        return {
            "type": "interact",
            "target": None,
            "details": {"action_type": "interact"},
            "server_endpoint": "actions",
        }

    # Explore intent
    explore_keywords = ["explore", "search", "look around", "investigate", "examine", "inspect"]
    if any(kw in msg for kw in explore_keywords):
        return {
            "type": "explore",
            "target": None,
            "details": {"action_type": "explore"},
            "server_endpoint": "actions",
        }

    # Puzzle intent
    puzzle_keywords = ["solve", "puzzle", "place", "use item", "put"]
    if any(kw in msg for kw in puzzle_keywords):
        return {
            "type": "puzzle",
            "target": None,
            "details": {"action_type": "puzzle"},
            "server_endpoint": "actions",
        }

    # Default: general turn
    return {
        "type": "general",
        "target": None,
        "details": {"intent": player_message},
        "server_endpoint": "turn",
    }


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
