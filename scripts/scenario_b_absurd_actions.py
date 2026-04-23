#!/usr/bin/env python3
"""
Scenario B Playtest — DM Intent Routing for Absurd Actions
==========================================================
Tests ISSUE-005: DM should refuse impossible actions, not misroute as movement.

Scenarios to test:
- "I swallow the statue" — should be refused, not traveled
- "I fly to the moon using my bare hands" — should be refused
- absurd travel queries — should refuse, not misroute to wrong location
"""

import httpx
import json
import os
import uuid
from datetime import datetime

RULES_URL = os.environ.get("D20_RULES_URL", "https://d20.holocronlabs.ai")
DM_URL = os.environ.get("DM_URL", "https://d20.holocronlabs.ai")
TIMEOUT = 30.0

CHAR_NAME = f"AbsurdTest-{uuid.uuid4().hex[:6]}"

transcript = []
flags_capture = {}

def log(kind, msg, data=None):
    entry = {"timestamp": datetime.utcnow().isoformat(), "kind": kind, "message": msg}
    if data is not None:
        entry["data"] = data if isinstance(data, (dict, list)) else str(data)
    transcript.append(entry)
    print(f"[{kind.upper()}] {msg}")

def main():
    print("=== D20 Scenario B: Absurd Action Intent Routing ===\n")
    print(f"Rules: {RULES_URL}")
    print(f"DM:    {DM_URL}")
    print(f"Char:  {CHAR_NAME}\n")

    with httpx.Client(timeout=TIMEOUT) as client:
        # Health checks
        try:
            r_health = client.get(f"{RULES_URL}/health", timeout=10)
            r_dm_health = client.get(f"{DM_URL}/dm/health", timeout=10)
            log("health", f"Rules: {r_health.status_code}, DM: {r_dm_health.status_code}")
        except Exception as e:
            log("error", f"Health check failed: {e}")
            return

        # Phase 1 — Create character
        payload = {"name": CHAR_NAME, "race": "Human", "class": "Fighter", "background": "Soldier"}
        r = client.post(f"{RULES_URL}/characters", json=payload, timeout=TIMEOUT)
        if r.status_code != 201:
            log("error", f"Character creation failed [{r.status_code}]: {r.text[:200]}")
            return
        char_id = r.json()["id"]
        log("create", f"Character created: {char_id}", {"char": r.json()})

        # Get starting location
        char = client.get(f"{RULES_URL}/characters/{char_id}", timeout=TIMEOUT).json()
        log("location", f"Starting location: {char.get('location_id', 'unknown')}")

        # Phase 2 — Get flags baseline
        r_flags = client.get(f"{RULES_URL}/narrative/flags/{char_id}", timeout=TIMEOUT)
        if r_flags.status_code == 200:
            flags_capture = r_flags.json()
            log("flags", f"Initial flags: {flags_capture}")

        # Phase 3 — Test absurd action 1: "I swallow the statue"
        log("test", "\n--- Test 1: Swallow statue ---")
        absurd1 = client.post(f"{DM_URL}/dm/turn", json={
            "character_id": char_id,
            "message": "I swallow the statue in the town square."
        }, timeout=60.0)
        resp1 = absurd1.json()
        narration1 = resp1.get("narration", {})
        scene1 = narration1.get("scene", "") if isinstance(narration1, dict) else str(narration1)
        choices1 = resp1.get("choices", [])
        log("dm_absurd1", f"Status: {absurd1.status_code}", {
            "scene_excerpt": scene1[:300],
            "choices_count": len(choices1),
            "choices": [c.get("label", str(c)) for c in choices1] if choices1 else []
        })
        # Check if it's misrouted to movement (BAD) vs refused (GOOD)
        is_misrouted = ("travel" in scene1.lower() or "move" in scene1.lower() or "can't reach" in scene1.lower()) and not any(refusal in scene1.lower() for refusal in ["can't", "cannot", "impossible", "too large", "no", "refuse"])
        is_refused = any(phrase in scene1.lower() for phrase in ["can't", "cannot", "impossible", "too large", "solid", "refuse"])
        log("analysis", f"Absurd1 analysis: misrouted={is_misrouted}, refused={is_refused}")

        # Phase 4 — Test absurd action 2: "I fly to the moon using my bare hands"
        log("test", "\n--- Test 2: Fly to moon ---")
        absurd2 = client.post(f"{DM_URL}/dm/turn", json={
            "character_id": char_id,
            "message": "I fly to the moon using my bare hands."
        }, timeout=60.0)
        resp2 = absurd2.json()
        narration2 = resp2.get("narration", {})
        scene2 = narration2.get("scene", "") if isinstance(narration2, dict) else str(narration2)
        choices2 = resp2.get("choices", [])
        log("dm_absurd2", f"Status: {absurd2.status_code}", {
            "scene_excerpt": scene2[:300],
            "choices_count": len(choices2)
        })
        is_misrouted2 = ("travel" in scene2.lower() or "moon" in scene2.lower()) and not any(refusal in scene2.lower() for refusal in ["can't", "cannot", "impossible", "no"])
        is_refused2 = any(phrase in scene2.lower() for phrase in ["can't", "cannot", "impossible", "can not"])
        log("analysis", f"Absurd2 analysis: misrouted={is_misrouted2}, refused={is_refused2}")

        # Phase 5 — Valid normal interactions (control)
        log("test", "\n--- Control: Statue query ---")
        dm_statue = client.post(f"{DM_URL}/dm/turn", json={
            "character_id": char_id,
            "message": "I examine the statue carefully."
        }, timeout=60.0)
        resp_statue = dm_statue.json()
        scene_statue = resp_statue.get("narration", {}).get("scene", "")
        log("dm_control", f"Statue query response", {"excerpt": scene_statue[:300]})

        # Phase 6 — Check combat choices for ISSUE-001
        log("test", "\n--- Issue 001 check: Combat choices ---")
        # First trigger combat
        r_flags_final = client.get(f"{RULES_URL}/narrative/flags/{char_id}", timeout=TIMEOUT)
        if r_flags_final.status_code == 200:
            flags_capture = r_flags_final.json()
            log("final_flags", f"Flags after tests: {flags_capture}")

        # Save transcript
        report = {
            "playthrough_id": str(uuid.uuid4()),
            "character_name": CHAR_NAME,
            "character_id": char_id,
            "timestamp": datetime.utcnow().isoformat(),
            "rules_url": RULES_URL,
            "dm_url": DM_URL,
            "transcript": transcript,
            "final_flags": flags_capture,
            "summary": "Scenario B: Absurd action intent routing test"
        }
        outfile = f"playthrough_{char_id}_scenarioB.json"
        with open(outfile, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved: {outfile}")
        print("=== COMPLETE ===")

if __name__ == "__main__":
    main()
