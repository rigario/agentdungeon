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
    def test_dm_runtime_root(self, dm):
        r = dm.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "d20-dm-runtime"


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
# 7. Cadence status
# ---------------------------------------------------------------------------

class TestCadence:
    """Verify cadence endpoint is available."""

    def test_cadence_status(self, rules):
        r = rules.get("/cadence/status")
        assert r.status_code == 200
        data = r.json()
        assert "config" in data or "global_stats" in data
