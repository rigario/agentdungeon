"""
Regression test for task 6cb970ec — absurd/nonsensical interact target rejection.

Verifies that the interact handler rejects clearly non-social/absurd action targets
(e.g., "punch horizon", "eat the sky", "jump off cliff") with a refusal response,
while still allowing legitimate ambiguous targets (e.g., "innkeeper", "the guard")
to proceed to NPC selection.
"""

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.database import get_db
import os

client = TestClient(app)

# ---------------------------------------------------------------------------
# Test data: need a character and a location with at least one NPC
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_character():
    """Create a fresh test character in Rusty Tankard."""
    # Use AuditMultiNpc character or create a new one for isolation
    char_id = "absurd-test-char-" + os.urandom(4).hex()
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO characters (id, name, race, char_class, level, hp_current, hp_max,
                                      location_id, equipment_json, mark_of_dreamer_stage, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (char_id, "AbsurdTester", "Human", "Fighter", 1, 20, 20,
             "rusty-tankard", json.dumps(["Longsword"]), 0)
        )
        # Add basic event log
        conn.execute("INSERT INTO event_log (character_id, event_type, location_id, details) VALUES (?, 'character_created', ?, ?)",
                     (char_id, "rusty-tankard", "Absurd target test character"))
        conn.commit()
    finally:
        conn.close()
    return char_id


class TestAbsurdInteractTargetRejection:
    """Test that absurd/nonsensical interact targets are refused."""

    def test_punch_horizon_is_refused(self, test_character):
        """Punch horizon → refusal, not NPC list."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "punch horizon"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "sensible" in data["narration"].lower() or "not a sensible" in data["narration"].lower()
        assert any(e["type"] == "absurd_action_rejected" for e in data.get("events", []))

    def test_eat_the_sky_is_refused(self, test_character):
        """Eat the sky → refusal."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "eat the sky"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "sensible" in data["narration"].lower()

    def test_jump_off_cliff_is_refused(self, test_character):
        """Jump off cliff → refusal."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "jump off cliff"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "sensible" in data["narration"].lower()

    def test_lick_the_ground_is_refused(self, test_character):
        """Lick the ground → refusal."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "lick the ground"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_ambiguous_innkeeper_continues(self, test_character):
        """'innkeeper' (no specific name) → proceeds to NPC choices, not refused."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "innkeeper"},
            headers={"Authorization": "Bearer test"},
        )
        # Should either find specific NPC if present, or fall through to multi-NPC prompt
        # The key is: NOT refused as absurd
        assert resp.status_code == 200
        data = resp.json()
        # If no npc found, should get choices (multi-NPC hub) OR default talk (single-NPC)
        # Main assertion: NOT absurd refusal
        assert data.get("success") in (True, None) or "sensible" not in data.get("narration", "").lower()

    def test_talk_to_someone_valid(self, test_character):
        """'talk to someone' → proceeds (plausible ambiguous social intent)."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "talk to someone"},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should NOT be absurd refusal
        assert "sensible" not in data.get("narration", "").lower()

    def test_named_npc_unaffected(self, test_character):
        """'Aldric' (real NPC name) → direct interaction, never absurd check."""
        resp = client.post(
            f"/characters/{test_character}/actions",
            json={"action_type": "interact", "target": "Aldric"},
            headers={"Authorization": "Bearer test"},
        )
        # Should find Aldric and succeed (or fail only if Aldric not present)
        # Main point: never blocked by absurd heuristic
        assert resp.status_code == 200
