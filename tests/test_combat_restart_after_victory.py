"""Regression: a character can start a second combat after resolving the first.

The combats table uses UNIQUE(character_id) to enforce one active combat per
character. A completed combat row used to remain in that table after victory,
so the next /combat/start attempted another row with the same character_id and
returned HTTP 500 from sqlite3.IntegrityError.
"""

import json
import os
import sys

from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [ROOT] + [p for p in sys.path if not p.endswith("dm-runtime")]

from app.main import app  # noqa: E402
from app.services.database import get_db  # noqa: E402


client = TestClient(app)


def _ensure_default_campaign():
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO campaigns (id, name, description) VALUES ('default', 'Default', 'Test default campaign')"
        )
        conn.commit()
    finally:
        conn.close()


def _start_training_combat(character_id: str, encounter_name: str):
    enemies = json.dumps([
        {
            "type": "Training Dummy",
            "count": 1,
            "hp": 1,
            "ac": 1,
            "attack_bonus": 0,
            "damage": "1d1",
            "initiative_mod": -10,
        }
    ])
    return client.post(
        f"/characters/{character_id}/combat/start",
        params={
            "encounter_name": encounter_name,
            "enemies_json": enemies,
            "initiative_roll": 20,
        },
        headers={"Authorization": "Bearer test"},
    )


def _win_training_combat(character_id: str):
    return client.post(
        f"/characters/{character_id}/combat/act",
        json={"action": "attack", "target_index": 0, "d20_roll": 20},
        headers={"Authorization": "Bearer test"},
    )


def test_character_can_start_second_combat_after_victory():
    _ensure_default_campaign()
    create = client.post(
        "/characters",
        json={"name": "CombatRestartProbe", "race": "Human", "class": "Fighter"},
        headers={"Authorization": "Bearer test"},
    )
    assert create.status_code in (200, 201)
    character_id = create.json()["id"]

    first = _start_training_combat(character_id, "Training One")
    assert first.status_code == 200, first.text
    first_win = _win_training_combat(character_id)
    assert first_win.status_code == 200, first_win.text
    assert first_win.json()["result"] == "victory"

    second = _start_training_combat(character_id, "Training Two")
    assert second.status_code == 200, second.text
    assert second.json()["combat_over"] is False

    second_win = _win_training_combat(character_id)
    assert second_win.status_code == 200, second_win.text
    assert second_win.json()["result"] == "victory"
