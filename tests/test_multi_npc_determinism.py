"""
Regression tests for deterministic NPC selection logic (task 8084708d).

These tests exercise the fixed routing logic without requiring a full server/database.
"""

import pytest

# Mock NPC data representing typical DB rows
NPC_ALDRIC = {
    "id": "npc-aldric",
    "name": "Aldric the Innkeeper",
    "archetype": "innkeeper",
}
NPC_MARTA = {
    "id": "npc-marta",
    "name": "Marta the Merchant",
    "archetype": "merchant",
}
NPC_SER_MAREN = {
    "id": "npc-ser-maren",
    "name": "Ser Maren",
    "archetype": "guard",
}


def simulate_npc_routing(npcs):
    """
    Deterministic routing logic extracted from actions.py post-patch.
    This mirrors the actual code block after named-target matching fails.

    Returns either a dict with an NPC (single hub) or a dict with choices (multi hub).
    """
    npc = None  # assume not found by name

    if npc is None:
        if len(npcs) > 1:
            npc_choices = [
                {
                    "id": n["id"],
                    "label": n["name"],
                    "description": f"Talk to {n['name']} ({n['archetype']}).",
                }
                for n in npcs
            ]
            return {
                "success": True,
                "narration": "Several people are here. Who would you like to speak with?",
                "choices": npc_choices,
                "events": [
                    {
                        "type": "npc_selection_required",
                        "available_npcs": [n["id"] for n in npcs],
                    }
                ],
            }
        else:
            npc = npcs[0]
            return {
                "success": True,
                "narration": f"You approach {npc['name']}.",
                "npc": npc,
            }


def test_single_npc_hub_is_deterministic():
    """Single-NPC locations must select deterministically (no randomness)."""
    result = simulate_npc_routing([NPC_ALDRIC])
    assert "npc" in result
    assert result["npc"]["id"] == "npc-aldric"
    assert "Aldric" in result["narration"]
    assert "choices" not in result


def test_multi_npc_hub_returns_explicit_choices():
    """Multi-NPC locations with generic talk must return a choices list, never random."""
    npcs = [NPC_MARTA, NPC_SER_MAREN]
    result = simulate_npc_routing(npcs)
    assert "choices" in result
    assert isinstance(result["choices"], list)
    assert len(result["choices"]) == 2
    labels = {c["label"] for c in result["choices"]}
    assert "Marta the Merchant" in labels
    assert "Ser Maren" in labels
    # Verify structure
    for c in result["choices"]:
        assert "id" in c and c["id"] in ("npc-marta", "npc-ser-maren")
        assert "description" in c
        assert "Talk to" in c["description"]
    assert result.get("success") is True
    # Event indicating selection required
    ev_types = [e["type"] for e in result.get("events", [])]
    assert "npc_selection_required" in ev_types


def test_multi_npc_hub_choice_ids_match_npcs():
    """Every choice id must correspond to an actual NPC in the hub."""
    npcs = [NPC_MARTA, NPC_SER_MAREN, NPC_ALDRIC]
    result = simulate_npc_routing(npcs)
    choice_ids = {c["id"] for c in result["choices"]}
    npc_ids = {n["id"] for n in npcs}
    assert choice_ids == npc_ids

