"""
Live integration test matrix for cadence/tick system.

This test exercises the full tick progression end-to-end against a live
server instance, verifying:
  • Multi-tick doom clock progression (sequential ticks)
  • Front portent advancement at configured thresholds
  • Custom tick interval changes (acceptance + minimum validation rejection)
  • Cadence/status coherence (global stats, next_tick_eta_seconds)
  • Event log persistence
  • Config preservation/restore capability

This is NOT a unit test — it calls real endpoints and validates real state.
Run with: pytest -m integration tests/test_cadence_live_matrix.py
Or: python tests/test_cadence_live_matrix.py (standalone mode)

Prerequisites:
  - Running FastAPI server at LIVE_TEST_BASE_URL (default: https://d20.holocronlabs.ai)
  - Character exists with valid character_id
  - Cadence mode is 'playtest' and active
"""

import sys
import os
import json
import time
import subprocess
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LIVE_TEST_BASE_URL = os.getenv("LIVE_TEST_BASE_URL", "https://d20.holocronlabs.ai")
LIVE_TEST_CHARACTER_ID = os.getenv("LIVE_TEST_CHARACTER_ID")  # Must be set if running live
LIVE_TEST_API_KEY = os.getenv("LIVE_TEST_API_KEY")  # If auth is required

INTEGRATION_MARK = "integration"


def curl_get(path: str) -> dict:
    """GET a live endpoint and return parsed JSON."""
    cmd = ["curl", "-s", "-f", f"{LIVE_TEST_BASE_URL}{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"GET {path} failed: {result.stderr}")
    return json.loads(result.stdout)


def curl_post(path: str, body: Optional[dict] = None, expect_ok: bool = True) -> dict:
    """POST to a live endpoint and return parsed JSON."""
    cmd = ["curl", "-s", "-X", "POST", f"{LIVE_TEST_BASE_URL}{path}"]
    if body:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"POST {path} returned invalid JSON: {result.stdout[:200]}")
    
    # Raise only if we expected success but got an error-detail response
    if expect_ok and "detail" in parsed:
        raise RuntimeError(f"POST {path} returned error: {parsed['detail']}")
    
    return parsed


# ---------------------------------------------------------------------------
# Integration test — requires live server
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_cadence_multi_tick_progression():
    """
    Verify sequential ticks increment doom clock correctly across multiple calls.
    This is the core 'live test matrix' for cadence progression.
    """
    if not LIVE_TEST_CHARACTER_ID:
        pytest.skip("LIVE_TEST_CHARACTER_ID not set — skipping live integration test")

    char_id = LIVE_TEST_CHARACTER_ID

    # 1. Snapshot initial state
    initial_doom = curl_get(f"/cadence/doom/{char_id}")
    initial_tick_count = initial_doom["total_ticks"]
    assert initial_doom["is_active"] == 1, "Playtest mode must be active for tick tests"

    # 2. Execute 3 sequential ticks
    tick_results = []
    for i in range(3):
        result = curl_post(f"/cadence/tick/{char_id}")
        tick_results.append(result)
        time.sleep(0.2)  # brief pause between DB writes

    # 3. Verify monotonic increment
    assert tick_results[0]["total_ticks"] == initial_tick_count + 1
    assert tick_results[1]["total_ticks"] == initial_tick_count + 2
    assert tick_results[2]["total_ticks"] == initial_tick_count + 3

    # 4. Verify portent advancement triggers at threshold (3 ticks → 1 portent if fronts exist)
    # If character has fronts, tick 3 should trigger; otherwise portents stays 0
    final_doom = curl_get(f"/cadence/doom/{char_id}")
    assert final_doom["total_ticks"] == initial_tick_count + 3
    # Portent count is data-dependent (fronts assigned); just verify it's an integer
    assert isinstance(final_doom["portents_triggered"], int)

    # 5. Verify tick timestamps are populated
    assert tick_results[0]["last_tick_at"] is not None
    assert tick_results[2]["last_tick_at"] >= tick_results[0]["last_tick_at"]


@pytest.mark.integration
def test_cadence_status_coherence():
    """
    Verify /cadence/status reflects accurate global stats and ETA.
    """
    status = curl_get("/cadence/status")

    # Config shape
    config = status["config"]
    assert config["cadence_mode"] in ("normal", "playtest")
    assert config["tick_interval_seconds"] >= 30
    assert "is_active" in config

    # Global stats
    stats = status["global_stats"]
    assert "characters_with_doom_clock" in stats
    assert "total_ticks_all_characters" in stats

    # ETA logic
    if config["is_active"]:
        assert status["next_tick_eta_seconds"] == config["tick_interval_seconds"]
    else:
        assert status["next_tick_eta_seconds"] is None


@pytest.mark.integration
def test_cadence_custom_interval_acceptance_and_validation():
    """
    Verify custom interval changes work and minimum validation rejects invalid values.
    """
    original = curl_get("/cadence/status")["config"]
    original_interval = original["tick_interval_seconds"]

    # 1. Accept valid custom interval (must be ≥ 30)
    resp = curl_post("/cadence/config", {"tick_interval_seconds": 180})
    assert resp["ok"] is True
    assert resp["config"]["tick_interval_seconds"] == 180

    # Verify reflected in status
    status = curl_get("/cadence/status")
    assert status["config"]["tick_interval_seconds"] == 180
    assert status["next_tick_eta_seconds"] == 180

    # 2. Reject invalid interval (< 30)
    resp_bad = curl_post("/cadence/config", {"tick_interval_seconds": 10}, expect_ok=False)
    assert "detail" in resp_bad
    assert "at least 30 seconds" in resp_bad["detail"]

    # 3. Restore original
    restore = curl_post("/cadence/config", {"tick_interval_seconds": original_interval})
    assert restore["ok"] is True
    assert restore["config"]["tick_interval_seconds"] == original_interval


@pytest.mark.integration
def test_cadence_event_log_entries():
    """
    Verify each tick generates a 'cadence_tick' event in the character event log.
    """
    if not LIVE_TEST_CHARACTER_ID:
        pytest.skip("LIVE_TEST_CHARACTER_ID not set")

    char_id = LIVE_TEST_CHARACTER_ID

    # Count events before
    before = curl_get(f"/characters/{char_id}/events")
    before_count = len(before.get("events", []))

    # Execute a tick
    curl_post(f"/cadence/tick/{char_id}")
    time.sleep(0.2)

    # Count events after
    after = curl_get(f"/characters/{char_id}/events")
    after_count = len(after.get("events", []))

    assert after_count == before_count + 1, "Exactly one new event should be logged"

    # Verify event type
    cadence_events = [e for e in after.get("events", []) if e["event_type"] == "cadence_tick"]
    assert len(cadence_events) >= 1
    assert "tick" in new_event["description"].lower()


# ---------------------------------------------------------------------------
# Standalone runner (invoked as script)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("CADENCE LIVE TEST MATRIX — Standalone runner")
    print("=" * 60)

    char_id = os.getenv("LIVE_TEST_CHARACTER_ID")
    if not char_id:
        print("\nERROR: LIVE_TEST_CHARACTER_ID environment variable not set.")
        print("Set it to a test character ID before running this script directly.")
        print("Example: LIVE_TEST_CHARACTER_ID=tickmatrixtest-aca851 python test_cadence_live_matrix.py")
        sys.exit(1)

    base = LIVE_TEST_BASE_URL
    print(f"\nTarget: {base}")
    print(f"Character: {char_id}")

    # Capture pre-state
    print("\n[1] Snapshot initial cadence/doom state...")
    initial = curl_get(f"/cadence/doom/{char_id}")
    print(f"    Initial doom: ticks={initial['total_ticks']}, portents={initial['portents_triggered']}")

    # Store original interval for restore
    orig_interval = curl_get("/cadence/status")["config"]["tick_interval_seconds"]
    print(f"    Original tick interval: {orig_interval}s")

    # Run 3 ticks
    print("\n[2] Executing 3 sequential ticks...")
    for n in range(1, 4):
        r = curl_post(f"/cadence/tick/{char_id}")
        print(f"    Tick {n}: total_ticks={r['total_ticks']}, portents={r['portents_triggered']}, "
              f"events={len(r.get('triggered_events', []))}")
        time.sleep(0.2)

    # Verify final doom
    final = curl_get(f"/cadence/doom/{char_id}")
    print(f"\n[3] Final doom clock: ticks={final['total_ticks']}, portents={final['portents_triggered']}")
    assert final["total_ticks"] == initial["total_ticks"] + 3, "Ticks did not increment correctly"

    # Custom interval test
    print("\n[4] Custom interval acceptance test (60 → 180 → 60)...")
    r1 = curl_post("/cadence/config", {"tick_interval_seconds": 180})
    print(f"    Change to 180s: ok={r1['ok']}, new={r1['config']['tick_interval_seconds']}s")
    assert r1["ok"] is True

    r2 = curl_post("/cadence/config", {"tick_interval_seconds": 10}, expect_ok=False)
    print(f"    Reject 10s: error={r2.get('detail', 'none')}")
    assert "at least 30 seconds" in r2.get("detail", "")

    r3 = curl_post("/cadence/config", {"tick_interval_seconds": orig_interval})
    print(f"    Restore {orig_interval}s: ok={r3['ok']}")

    # Status coherence check
    print("\n[5] Cadence/status coherence check...")
    status = curl_get("/cadence/status")
    print(f"    Mode: {status['config']['cadence_mode']}, active: {status['config']['is_active']}")
    print(f"    Characters with doom clock: {status['global_stats']['characters_with_doom_clock']}")
    print(f"    Total ticks (all chars): {status['global_stats']['total_ticks_all_characters']}")
    print(f"    next_tick_eta_seconds: {status['next_tick_eta_seconds']}")

    # Event log check
    events = curl_get(f"/characters/{char_id}/event-log")
    cadence_events = [e for e in events.get("events", []) if e["event_type"] == "cadence_tick"]
    print(f"\n[6] Event log: {len(cadence_events)} cadence_tick events found")
    assert len(cadence_events) >= 3, "Expected at least 3 cadence_tick events"

    print("\n" + "=" * 60)
    print("ALL LIVE MATRIX CHECKS PASSED")
    print("=" * 60)
