"""Regression coverage for ISSUE-021: lethal route encounters must not brick characters.

A level-1 character can lose a movement-triggered encounter before the demo route
reaches its story beats. Defeat is fine; persisting hp_current=0 is not, because
character validation rejects all future actions/DM turns as character_deceased.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [ROOT] + [p for p in sys.path if not p.endswith("dm-runtime")]

from app.routers import actions
from app.services.character_validation import validate_char_state


class _NoMarenConnection:
    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return None

    def close(self):
        pass


class _MaxRollRng:
    def randint(self, _low, high):
        return high


def test_resolve_combat_defeat_leaves_character_alive_for_recovery(monkeypatch):
    """A non-cave defeat should return wounded survival at 1 HP, not 0 HP."""
    monkeypatch.setattr(actions, "get_db", lambda: _NoMarenConnection())

    char = {
        "id": "issue-021-unit",
        "name": "Issue 021 Probe",
        "hp_current": 12,
        "hp_max": 12,
        "ac_value": 12,
        "ability_scores_json": '{"str": 10, "dex": 10}',
        "location_id": "south-road",
    }
    encounter = {
        "id": "enc-issue-021-lethal",
        "name": "Regression Ambush",
        "enemies": [
            {
                "type": "Ogre Regression",
                "count": 1,
                "hp": 99,
                "ac": 1,
                "attack_bonus": 99,
                "damage": "20d6",
                "initiative_mod": 99,
            }
        ],
        "loot": [],
    }

    result = actions._resolve_combat(char, encounter, _MaxRollRng())

    assert result["victory"] is False
    assert result["hp_remaining"] == 1
    assert any(event["type"] == "combat_defeat" for event in result["events"])
    assert any(event["type"] == "wounded_survival" for event in result["events"])


def test_wounded_survival_hp_passes_character_validation():
    """The recovery HP must clear the validation gate that previously caused 403s."""
    validation = validate_char_state(
        {
            "id": "issue-021-unit",
            "hp_current": 1,
            "hp_max": 12,
            "is_archived": 0,
        }
    )

    assert validation["valid"] is True
    assert validation.get("code") != "character_deceased"
