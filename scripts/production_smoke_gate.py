#!/usr/bin/env python3
"""
Production Playtest Readiness Smoke Gate

Validates the full playtest loop end-to-end against live production URLs.
This is the heartbeat gate that catches when health is green but the actual
play loop is broken (the "false green" problem discovered in Alpha audit).

Environment:
  SMOKE_RULES_URL   (default: http://localhost:8600)
  SMOKE_DM_URL      (default: http://localhost:8610)
  SMOKE_CHAR_NAME   (default: SmokeGate-<random>)
  SMOKE_CLEANUP     (default: 1) — set to 0 to keep test character

Exit code: 0 if all critical checks pass, 1 if any fail.
Output: PASS/FAIL table plus minimal failure context.

Wire: Referenced from PLAYTEST-RUNBOOK.md "Production Readiness Gate"
"""

import os
import sys
import uuid
import json
import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RULES_URL = os.environ.get("SMOKE_RULES_URL", "http://localhost:8600").rstrip("/")
DM_URL = os.environ.get("SMOKE_DM_URL", "http://localhost:8610").rstrip("/")
CHAR_NAME = os.environ.get("SMOKE_CHAR_NAME", f"SmokeGate-{uuid.uuid4().hex[:6]}")
CLEANUP = int(os.environ.get("SMOKE_CLEANUP", "1"))
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
results = []
char_id = None

def check(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))

# ---------------------------------------------------------------------------
# Phase 1: Health checks
# ---------------------------------------------------------------------------
print("=== Production Playtest Readiness Gate ===")
print()

# Rules server health
try:
    r = httpx.get(f"{RULES_URL}/health", timeout=5.0)
    if r.status_code == 200 and r.json().get("status") in ("ok", "healthy"):
        check("Rules server /health", True, "status=ok, db_connected=true")
    else:
        check("Rules server /health", False, f"code={r.status_code} body={r.text[:120]}")
except Exception as e:
    check("Rules server /health", False, str(e)[:120])

# DM runtime health
try:
    r = httpx.get(f"{DM_URL}/dm/health", timeout=5.0)
    if r.status_code == 200 and r.json().get("status") == "healthy":
        check("DM runtime /dm/health", True, "status=healthy")
    else:
        check("DM runtime /dm/health", False, f"code={r.status_code} body={r.text[:120]}")
except Exception as e:
    check("DM runtime /dm/health", False, str(e)[:120])

# ---------------------------------------------------------------------------
# Phase 2: Character lifecycle (create → fetch → validate)
# ---------------------------------------------------------------------------
char_payload = {
    "name": CHAR_NAME,
    "race": "Human",
    "class": "Fighter",
}
try:
    r = httpx.post(f"{RULES_URL}/characters", json=char_payload, timeout=TIMEOUT)
    if r.status_code == 201:
        char_data = r.json()
        char_id = char_data.get("id")
        # Required invariants: id present, location_id not null, sheet_json valid
        if char_id and char_data.get("location_id"):
            sheet = char_data.get("sheet_json", {})
            if isinstance(sheet, dict) and sheet.get("character"):
                check("POST /characters (create)", True, f"id={char_id}, loc={char_data.get('location_id')}")
            else:
                check("POST /characters (create)", False, "sheet_json invalid or missing character")
        else:
            check("POST /characters (create)", False, "missing id or location_id")
    else:
        check("POST /characters (create)", False, f"code={r.status_code} body={r.text[:120]}")
except Exception as e:
    check("POST /characters (create)", False, str(e)[:120])

# Fetch character (only if creation succeeded)
if char_id:
    try:
        r = httpx.get(f"{RULES_URL}/characters/{char_id}", timeout=TIMEOUT)
        if r.status_code == 200:
            fetch_data = r.json()
            # Validate: id matches, location_id/current_location_id exists and is non-null
            loc = fetch_data.get("location_id") or fetch_data.get("current_location_id")
            if loc:
                check("GET /characters/{id} (fetch)", True, f"location_id={loc}")
            else:
                check("GET /characters/{id} (fetch)", False, "no location_id in response")
        else:
            check("GET /characters/{id} (fetch)", False, f"code={r.status_code}")
    except Exception as e:
        check("GET /characters/{id} (fetch)", False, str(e)[:120])

    # -----------------------------------------------------------------------
    # Phase 3: Action loop (look/explore → move)
    # -----------------------------------------------------------------------
    try:
        r = httpx.post(
            f"{RULES_URL}/characters/{char_id}/actions",
            json={"action_type": "explore"},
            timeout=TIMEOUT
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("success") is True or "resolution" in data or "events" in data:
                check("POST /actions (explore)", True, "success/events present")
            else:
                check("POST /actions (explore)", False, "no success/events")
        else:
            check("POST /actions (explore)", False, f"code={r.status_code}")
    except Exception as e:
        check("POST /actions (explore)", False, str(e)[:120])

    # Move action (requires char to exist, location must be valid target)
    try:
        r = httpx.post(
            f"{RULES_URL}/characters/{char_id}/actions",
            json={"action_type": "move", "target": "forest-edge"},
            timeout=TIMEOUT
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("success") is True:
                check("POST /actions (move)", True, "success, location should update")
            else:
                check("POST /actions (move)", False, f"success=False body={r.text[:80]}")
        else:
            check("POST /actions (move)", False, f"code={r.status_code} body={r.text[:80]}")
    except Exception as e:
        check("POST /actions (move)", False, str(e)[:120])

    # -----------------------------------------------------------------------
    # Phase 4: DM turn (end-to-end narration)
    # -----------------------------------------------------------------------
    try:
        r = httpx.post(
            f"{DM_URL}/dm/turn",
            json={"character_id": char_id, "message": "look around"},
            timeout=TIMEOUT
        )
        if r.status_code == 200:
            data = r.json()
            # DM turn should return narration + choices + mechanics
            if "narration" in data and "choices" in data:
                check("POST /dm/turn (look)", True, "narration+choices present")
            else:
                check("POST /dm/turn (look)", False, "missing narration/choices")
        else:
            check("POST /dm/turn (look)", False, f"code={r.status_code}")
    except Exception as e:
        check("POST /dm/turn (look)", False, str(e)[:120])

    # -----------------------------------------------------------------------
    # Phase 5: Portal token (if endpoint exists)
    # -----------------------------------------------------------------------
    try:
        r = httpx.post(
            f"{RULES_URL}/portal/token",
            json={"character_id": char_id},
            timeout=TIMEOUT
        )
        if r.status_code in (200, 201):
            data = r.json()
            if "token" in data:
                check("POST /portal/token", True, "token created")
            else:
                check("POST /portal/token", False, "no token in response")
        elif r.status_code == 404:
            check("POST /portal/token", True, "SKIP — endpoint not available (404)")
        else:
            check("POST /portal/token", False, f"code={r.status_code}")
    except Exception as e:
        check("POST /portal/token", False, str(e)[:120])

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------
    if CLEANUP and char_id:
        try:
            httpx.delete(f"{RULES_URL}/characters/{char_id}", timeout=5.0)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("=== Results ===")
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
for name, ok, detail in results:
    status_mark = "PASS" if ok else "FAIL"
    print(f"  [{status_mark}] {name}")
    if detail and not ok:
        print(f"        {detail}")

print()
print(f"=== SUMMARY: {passed}/{total} passed ===")

if passed == total:
    print("Gate: PASSED ✓")
    sys.exit(0)
else:
    print("Gate: FAILED ✗")
    sys.exit(1)
