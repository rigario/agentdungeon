"""
Test for thornhold_statue_observed flag — acceptance test for task 58e1f315.

Validates that exploring in Thornhold sets the narrative flag required for
the antechamber puzzle access (d572bb09).
"""

import os
import httpx
import pytest
import uuid

RULES_URL = os.environ.get("SMOKE_RULES_URL", "http://localhost:8600")
TIMEOUT = 30.0


@pytest.fixture(scope="session")
def rules_client():
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="session")
def test_character_id(rules_client):
    """Create a throwaway test character and return its ID."""
    payload = {
        "name": f"StatueTest-{uuid.uuid4().hex[:6]}",
        "race": "Human",
        "class": "Fighter",
    }
    r = rules_client.post("/characters", json=payload)
    assert r.status_code == 201, f"Character creation failed: {r.text}"
    char_id = r.json()["id"]
    yield char_id
    # Cleanup
    try:
        rules_client.delete(f"/characters/{char_id}")
    except Exception:
        pass


def test_thornhold_statue_observed_flag_set(rules_client, test_character_id):
    """
    Acceptance criterion for task 58e1f315:
    
    1. Character explores in Thornhold (default start location)
    2. The thornhold_statue_observed narrative flag is set
    3. Flag is visible via /narrative/flags/{id} endpoint
    
    Fixes: "Exploring Thornhold 5+ times does not set thornhold_statue_observed"
    After fix: flag sets on FIRST explore in Thornhold.
    """
    char_id = test_character_id
    
    # Character starts in thornhold by default
    # One explore triggers the statue observation logic
    r = rules_client.post(f"/characters/{char_id}/actions", json={
        "action_type": "explore",
    })
    assert r.status_code == 200, f"Explore action failed: {r.text}"
    
    # Fetch narrative flags via the public endpoint
    r2 = rules_client.get(f"/narrative/flags/{char_id}")
    assert r2.status_code == 200, f"Flags endpoint failed: {r2.text}"
    
    flags_data = r2.json()
    # flags_data is a dict of flag_key -> flag_value
    assert isinstance(flags_data, dict), f"Expected dict, got {type(flags_data)}"
    
    assert "thornhold_statue_observed" in flags_data, (
        f"thornhold_statue_observed flag NOT set after explore in Thornhold. "
        f"Expected flag in response but got keys: {list(flags_data.keys())}"
    )
    
    # Verify the flag value is truthy
    flag_val = flags_data["thornhold_statue_observed"]
    assert flag_val in ("1", 1, "true", True, "yes", "set"), (
        f"thornhold_statue_observed has unexpected value: {flag_val}"
    )
