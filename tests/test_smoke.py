"""Playtest Smoke Suite — critical-path integration tests.

Validates the core playtest loop:
  1. Health check (rules server)
  2. Character create
  3. DM runtime health (if reachable)
  4. One exploration step
  5. One combat round
  6. DM turn (if runtime reachable)
  7. Persistence / resume

All tests hit a running server — no mocks. Configure base URLs via env:
  SMOKE_RULES_URL   (default http://localhost:8600)
  SMOKE_DM_URL      (default http://localhost:8610)

Run:  pytest tests/test_smoke.py -v --tb=short
"""

import os
import uuid

import httpx
import pytest

RULES_URL = os.environ.get("SMOKE_RULES_URL", "http://localhost:8600")
DM_URL = os.environ.get("SMOKE_DM_URL", "http://localhost:8610")
TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dm_reachable() -> bool:
    """Check if DM runtime is reachable."""
    try:
        r = httpx.get(f"{DM_URL}/", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _world_seeded() -> bool:
    """Check if rules server has seed data (locations exist)."""
    try:
        r = httpx.get(f"{RULES_URL}/health", timeout=3.0)
        if r.status_code != 200:
            return False
        # Check locations — endpoint returns dict with 'npcs' key or list
        r2 = httpx.get(f"{RULES_URL}/npcs/locations", timeout=3.0)
        if r2.status_code != 200:
            return False
        data = r2.json()
        if isinstance(data, dict):
            return data.get("count", 0) > 0 or len(data.get("npcs", [])) > 0
        return len(data) > 0
    except Exception:
        return False


skip_no_dm = pytest.mark.skipif(not _dm_reachable(), reason="DM runtime not reachable")
skip_no_seed = pytest.mark.skipif(not _world_seeded(), reason="World seed data not present")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rules():
    """httpx client for the rules server."""
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def dm():
    """httpx client for the DM runtime."""
    with httpx.Client(base_url=DM_URL, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def character(rules):
    """Create a throwaway test character and return its ID."""
    payload = {
        "name": f"Smoke-{uuid.uuid4().hex[:6]}",
        "race": "Human",
        "class": "Fighter",
    }
    r = rules.post("/characters", json=payload)
    assert r.status_code == 201, f"Character creation failed [{r.status_code}]: {r.text}"
    char = r.json()
    char_id = char["id"]
    # Validate spawn location exists in world state (P1 bug fix: should be valid, not 'thornhold' missing)
    spawn_loc = char.get("location_id")
    assert spawn_loc == "rusty-tankard", \
        f"Fresh character must spawn at 'rusty-tankard' (valid location), got: {spawn_loc}"
    yield char_id
    # Cleanup — best effort
    try:
        rules.delete(f"/characters/{char_id}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. Health checks
# ---------------------------------------------------------------------------

class TestHealth:
    """Basic service availability."""

    def test_rules_server_health(self, rules):
        r = rules.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["db_connected"] is True

    def test_rules_server_root(self, rules):
        r = rules.get("/")
        assert r.status_code == 200
        # Root now serves landing page HTML, not JSON API response
        assert "text/html" in r.headers.get("content-type", "")

    @skip_no_dm
    def test_dm_runtime_health(self, dm):
        r = dm.get("/dm/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["dm_runtime"] == "ok"
        rs = data.get("rules_server", {})
        assert rs.get("status") == "ok" or rs.get("db_connected") is True

    @skip_no_dm
    def test_dm_runtime_health(self, dm):
        """DM runtime health check — uses /dm/health (not / which may be routed to rules server)."""
        r = dm.get("/dm/health")
        assert r.status_code == 200
        data = r.json()
        assert data["dm_runtime"] == "ok"
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# 2. Character create + fetch
# ---------------------------------------------------------------------------

class TestCharacterCreate:
    """Character CRUD basics."""

    def test_create_fighter(self, rules):
        """Create a Human Fighter."""
        r = rules.post("/characters", json={
            "name": f"Fighter-{uuid.uuid4().hex[:6]}",
            "race": "Human",
            "class": "Fighter",
        })
        assert r.status_code == 201
        char = r.json()
        assert char["name"].startswith("Fighter-")
        assert char["race"]["name"] == "Human"
        assert any(c["name"] == "Fighter" for c in char["classes"])
        # Cleanup
        rules.delete(f"/characters/{char['id']}")

    def test_create_wizard(self, rules):
        """Create an Elf Wizard."""
        r = rules.post("/characters", json={
            "name": f"Wizard-{uuid.uuid4().hex[:6]}",
            "race": "Elf",
            "class": "Wizard",
        })
        assert r.status_code == 201
        char = r.json()
        assert char["race"]["name"] == "Elf"
        assert any(c["name"] == "Wizard" for c in char["classes"])
        rules.delete(f"/characters/{char['id']}")

    def test_invalid_race_rejected(self, rules):
        r = rules.post("/characters", json={
            "name": "BadRace",
            "race": "Klingon",
            "class": "Fighter",
        })
        assert r.status_code in (400, 422)

    def test_missing_class_rejected(self, rules):
        r = rules.post("/characters", json={
            "name": "NoClass",
            "race": "Human",
        })
        assert r.status_code == 422

    def test_fetch_character(self, rules, character):
        r = rules.get(f"/characters/{character}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == character
        assert "race" in data
        assert "classes" in data


# ---------------------------------------------------------------------------
# 3. Exploration step
# ---------------------------------------------------------------------------

class TestExploration:
    """Explore action — loot search, atmosphere."""

    @skip_no_seed
    def test_explore_action(self, rules, character):
        r = rules.post(f"/characters/{character}/actions", json={
            "action_type": "explore",
        })
        assert r.status_code == 200
        data = r.json()
        # Should have resolution or events
        assert "resolution" in data or "events" in data


# ---------------------------------------------------------------------------
# 4. Combat round
# ---------------------------------------------------------------------------

class TestCombat:
    """Attack → combat round → verify combat state or resolution."""

    @skip_no_seed
    def test_attack_action(self, rules, character):
        """Submit an attack action. May trigger combat or resolve immediately."""
        r = rules.post(f"/characters/{character}/actions", json={
            "action_type": "attack",
        })
        assert r.status_code == 200
        data = r.json()
        assert "resolution" in data or "events" in data


# ---------------------------------------------------------------------------
# 5. DM runtime turn
# ---------------------------------------------------------------------------

class TestDMTurn:
    """End-to-end: player message → DM runtime → rules server → narrated output."""

    @skip_no_dm
    def test_explore_turn(self, dm, character):
        """Send an exploration intent through the DM runtime."""
        r = dm.post("/dm/turn", json={
            "character_id": character,
            "message": "look around and search for loot",
        })
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            data = r.json()
            assert "narration" in data
            assert "mechanics" in data
            assert "choices" in data

    @skip_no_dm
    def test_move_turn(self, dm, character):
        """Send a move intent through the DM runtime."""
        r = dm.post("/dm/turn", json={
            "character_id": character,
            "message": "go to the tavern",
        })
        assert r.status_code in (200, 502)

    @skip_no_dm
    def test_missing_character_id(self, dm):
        """Missing character_id should return 400."""
        r = dm.post("/dm/turn", json={
            "message": "hello",
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 6. Persistence / resume
# ---------------------------------------------------------------------------

class TestPersistence:
    """Character state survives across separate requests."""

    @skip_no_seed
    def test_character_persists(self, rules):
        """Create → fetch → verify same character across requests."""
        name = f"Persist-{uuid.uuid4().hex[:8]}"
        r1 = rules.post("/characters", json={"name": name, "race": "Human", "class": "Rogue"})
        assert r1.status_code == 201
        char_id = r1.json()["id"]

        # Fetch in a fresh request
        r2 = rules.get(f"/characters/{char_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == char_id
        assert r2.json()["name"] == name

        # Explore to generate an event
        r3 = rules.post(f"/characters/{char_id}/actions", json={
            "action_type": "explore",
        })
        assert r3.status_code == 200

        # Fetch event log — should have entries
        r4 = rules.get(f"/characters/{char_id}/event-log")
        assert r4.status_code == 200
        log = r4.json()
        # Event log may return dict with 'events' key or a list
        events = log.get("events", log) if isinstance(log, dict) else log
        assert len(events) > 0

        # Cleanup
        rules.delete(f"/characters/{char_id}")

    def test_event_log_since_filter(self, rules, character):
        """Event log supports ?since= filtering."""
        r = rules.get(f"/characters/{character}/event-log", params={"since": "2020-01-01T00:00:00"})
        assert r.status_code == 200
        log = r.json()
        events = log.get("events", log) if isinstance(log, dict) else log
        assert isinstance(events, list)
        assert len(events) > 0


# ---------------------------------------------------------------------------
# 6b. Location persistence regression (ISSUE-007)
# ---------------------------------------------------------------------------

class TestLocationPersistence:
    """Regression test for ISSUE-007: character location_id must persist after move action.

    Verifies that POST /characters/{id}/actions with action_type='move' correctly
    updates the character's location_id in the database, and that subsequent GET
    reflects the new location. This guards against the bug where location_id was
    not updated, causing current_location_id to remain stale.
    """

    @skip_no_seed
    def test_move_updates_location_id(self, rules, character):
        """Move action should update character's location_id to target location."""
        # 1. Get initial character state
        r_initial = rules.get(f"/characters/{character}")
        assert r_initial.status_code == 200
        initial_data = r_initial.json()
        start_location = initial_data.get("location_id")
        assert start_location is not None, "Character must have an initial location"

        # 2. Determine a valid connected location to move to
        # From world seed: rusty-tankard connects to thornhold
        # This is derived from app/scripts/seed.py LOCATIONS constant
        START_LOCATION_CONNECTIONS = {
            "rusty-tankard": ["thornhold"],
            "thornhold": ["forest-edge", "south-road"],
            "forest-edge": ["deep-forest", "thornhold"],
            "south-road": ["crossroads", "thornhold"],
            "deep-forest": ["forest-edge", "cave-entrance"],
            "crossroads": ["south-road", "greypeak-pass"],
            "greypeak-pass": ["crossroads"],
            "cave-entrance": ["deep-forest", "cave-depths"],
            "cave-depths": ["cave-entrance", "seal-chamber"],
            "seal-chamber": ["cave-depths"],
        }
        connected = START_LOCATION_CONNECTIONS.get(start_location)
        assert connected, f"Unknown start location '{start_location}' — add to connection map"
        target_location = connected[0]

        # 3. Perform move action
        r_move = rules.post(
            f"/characters/{character}/actions",
            json={"action_type": "move", "target": target_location}
        )
        assert r_move.status_code == 200, f"Move action failed [{r_move.status_code}]: {r_move.text}"
        move_data = r_move.json()
        assert move_data.get("success") is True, f"Move returned success=False: {move_data}"

        # 4. Verify character location updated
        r_after = rules.get(f"/characters/{character}")
        assert r_after.status_code == 200
        after_data = r_after.json()
        new_location = after_data.get("location_id")

        assert new_location == target_location, (
            f"Location persistence failed: after move to '{target_location}', "
            f"character location_id is '{new_location}' (expected '{target_location}')"
        )

        # 5. Verify current_location_id alias matches
        assert after_data.get("current_location_id") == target_location, (
            f"current_location_id mismatch: expected '{target_location}', got '{after_data.get('current_location_id')}'"
        )

        # 6. Verify event_log contains the move
        r_log = rules.get(f"/characters/{character}/event-log")
        assert r_log.status_code == 200
        log_data = r_log.json()
        events = log_data.get("events", log_data) if isinstance(log_data, dict) else log_data
        move_events = [e for e in events if e.get("event_type") == "move" and e.get("location_id") == target_location]
        assert len(move_events) >= 1, f"No move event found in log for target '{target_location}'"


# ---------------------------------------------------------------------------
# 7. Cadence status
# ---------------------------------------------------------------------------

class TestCadence:
    """Verify cadence endpoint is available."""

    def test_cadence_status(self, rules):
        r = rules.get("/cadence/status")
        assert r.status_code == 200
        data = r.json()
        assert "config" in data or "global_stats" in data


# ---------------------------------------------------------------------------
# 8. Portal sharing
# ---------------------------------------------------------------------------

class TestPortal:
    """Portal share token creation and view rendering."""

    def test_create_portal_token(self, rules, character):
        """POST /portal/token creates a share token for a character."""
        r = rules.post("/portal/token", json={"character_id": character})
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        # Verify response fields exist
        assert "id" in data, "Missing 'id' in response"
        assert "token" in data, "Missing 'token' in response"
        assert data["character_id"] == character, "Character ID mismatch"
        assert "character_name" in data, "Missing 'character_name' in response"

    def test_portal_token_view(self, rules, character):
        """GET /portal/{token}/view returns HTML portal page."""
        # Create a token first
        create_r = rules.post("/portal/token", json={"character_id": character})
        assert create_r.status_code == 201, f"Token creation failed: {create_r.text}"
        token = create_r.json()["token"]

        # GET the portal view
        r = rules.get(f"/portal/{token}/view")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        # Should be HTML
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"Expected HTML content-type, got {ct}"
        # Basic content check: page should not be empty
        assert len(r.text) > 100, "Portal view response appears empty or minimal"
