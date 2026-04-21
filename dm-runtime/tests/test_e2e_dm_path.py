"""End-to-end DM path integration tests.

Tests the full pipeline: player message → DM runtime → rules server → narrated response.
Requires both rules server (port 8600) and DM runtime (port 8610) to be running.

Run: pytest tests/test_e2e_dm_path.py -v
Skip if servers not running: pytest tests/test_e2e_dm_path.py -v -m "not e2e"
"""

import pytest
import httpx
import time

RULES_URL = "http://localhost:8600"
DM_URL = "http://localhost:8610"


def _servers_running() -> bool:
    """Check if both servers are reachable."""
    try:
        with httpx.Client(timeout=5) as c:
            c.get(f"{RULES_URL}/health")
            c.get(f"{DM_URL}/dm/health")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _servers_running(),
    reason="Rules server (8600) and/or DM runtime (8610) not running"
)


@pytest.fixture(scope="module")
def character_id():
    """Create a test character for the integration tests."""
    with httpx.Client(timeout=30) as c:
        # Create character
        resp = c.post(f"{DM_URL}/dm/character", json={
            "name": f"E2E-Test-{int(time.time())}",
            "race": "Human",
            "class": "Fighter",
            "background": "Soldier",
        })
        assert resp.status_code == 200, f"Failed to create character: {resp.text}"
        data = resp.json()
        cid = data.get("id")
        assert cid, f"No character ID in response: {data}"
        yield cid


class TestDMHealth:
    """Verify DM runtime health and connectivity."""

    def test_dm_health_ok(self):
        with httpx.Client(timeout=10) as c:
            resp = c.get(f"{DM_URL}/dm/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["dm_runtime"] == "ok"
            assert data["rules_server"]["status"] == "ok"

    def test_dm_contract(self):
        with httpx.Client(timeout=10) as c:
            resp = c.get(f"{DM_URL}/dm/contract")
            assert resp.status_code == 200
            data = resp.json()
            assert data["contract_version"] == "1.0.0"
            assert "dm_owns" in data["authority"]
            assert "server_owns" in data["authority"]


class TestIntentClassification:
    """Verify intent classification for various player messages."""

    @pytest.mark.parametrize("message,expected_type,expected_endpoint", [
        ("go to thornhold", "move", "actions"),
        ("travel to the crossroads", "move", "actions"),
        ("attack the goblin", "combat", "combat"),
        ("fight!", "combat", "combat"),
        ("rest for the night", "rest", "actions"),
        ("take a short rest", "rest", "actions"),
        ("look around", "explore", "actions"),
        ("search the area", "explore", "actions"),
        ("cast fireball", "cast", "actions"),
        ("talk to the innkeeper", "talk", "actions"),
        ("examine the statue", "interact", "actions"),
        ("explore", "general", "turn"),  # single word → broad intent
        ("what now", "general", "turn"),
    ])
    def test_intent_classification(self, message, expected_type, expected_endpoint):
        with httpx.Client(timeout=10) as c:
            resp = c.post(f"{DM_URL}/dm/intent/analyze", json={"message": message})
            assert resp.status_code == 200
            data = resp.json()
            classification = data["classification"]
            assert classification["type"] == expected_type, \
                f"'{message}' → got {classification['type']}, expected {expected_type}"
            assert classification["server_endpoint"] == expected_endpoint, \
                f"'{message}' → got {classification['server_endpoint']}, expected {expected_endpoint}"


class TestEndToEndPaths:
    """Test the full player message → narrated response pipeline."""

    def test_explore_action(self, character_id):
        """Explore intent routes to actions/explore and returns valid DMResponse."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "look around and search",
            })
            assert resp.status_code == 200
            data = resp.json()

            # Validate DMResponse structure
            assert "narration" in data
            assert "mechanics" in data
            assert "choices" in data
            assert "server_trace" in data

            # Narration should have scene text
            assert data["narration"]["scene"], "Narration scene should not be empty"
            assert isinstance(data["narration"]["npc_lines"], list)
            assert data["narration"]["tone"] in [
                "neutral", "ominous", "hopeful", "tense", "mysterious", "triumphant"
            ]

            # Mechanics should have HP and location
            assert "hp" in data["mechanics"]
            assert "current" in data["mechanics"]["hp"]
            assert "max" in data["mechanics"]["hp"]
            assert data["mechanics"]["hp"]["max"] > 0, "HP max should be positive"
            assert data["mechanics"]["location"], "Location should not be empty"

            # Server trace should show correct endpoint
            assert data["server_trace"]["server_endpoint_called"] in ["actions", "turn"]

    def test_move_action(self, character_id):
        """Move intent routes to actions/move."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "go to crossroads",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["narration"]["scene"]
            assert data["server_trace"]["server_endpoint_called"] == "actions"

    def test_rest_action(self, character_id):
        """Rest intent routes to actions/rest."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "take a long rest",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["narration"]["scene"]
            assert data["server_trace"]["intent_used"]["type"] == "rest"

    def test_general_turn(self, character_id):
        """Broad intent routes to turn/start with choices returned."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "explore",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["narration"]["scene"]
            assert data["server_trace"]["server_endpoint_called"] == "turn/start"
            assert data["server_trace"]["turn_id"] is not None

    def test_combat_action(self, character_id):
        """Combat intent routes to combat/start."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "attack something!",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["narration"]["scene"]
            assert data["server_trace"]["server_endpoint_called"] in ["combat/start", "actions"]

    def test_missing_character_id(self):
        """Missing character_id returns 400."""
        with httpx.Client(timeout=10) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "message": "explore",
            })
            assert resp.status_code == 400

    def test_invalid_character(self):
        """Invalid character_id returns error."""
        with httpx.Client(timeout=30) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": "nonexistent-character-id",
                "message": "explore",
            })
            # Should return 502 (upstream error) not crash
            assert resp.status_code in [404, 502]


class TestDMResponseContract:
    """Validate that DM responses conform to the contract schema."""

    def test_response_has_all_fields(self, character_id):
        """DMResponse must have narration, mechanics, choices, server_trace."""
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{DM_URL}/dm/turn", json={
                "character_id": character_id,
                "message": "look around",
            })
            assert resp.status_code == 200
            data = resp.json()

            # Required fields
            required = ["narration", "mechanics", "choices", "server_trace"]
            for field in required:
                assert field in data, f"Missing required field: {field}"

            # Narration sub-fields
            assert "scene" in data["narration"]
            assert "npc_lines" in data["narration"]
            assert "tone" in data["narration"]

            # Mechanics sub-fields
            assert "what_happened" in data["mechanics"]
            assert "hp" in data["mechanics"]
            assert "location" in data["mechanics"]

            # Choices is a list
            assert isinstance(data["choices"], list)

            # Server trace sub-fields
            assert "server_endpoint_called" in data["server_trace"]
            assert "intent_used" in data["server_trace"]
