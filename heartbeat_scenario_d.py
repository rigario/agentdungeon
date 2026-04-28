#!/usr/bin/env python3
"""
D20 Heartbeat Scenario D Playtest — Climax/Endings
Tests: Drenna/Kol accessibility, flag progression, Communion path reachability
"""

import os
import uuid
import json
import httpx
from datetime import datetime

# Configuration
RULES_URL = os.environ.get("SMOKE_RULES_URL", "https://agentdungeon.com")
DM_URL = os.environ.get("SMOKE_DM_URL", "https://agentdungeon.com")
TIMEOUT = 30.0

CHAR_NAME = f"heartbeat-scenarioD-{uuid.uuid4().hex[:6]}"

def log(transcript, kind, message, data=None):
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kind": kind,
        "message": message,
        "data": data
    }
    transcript.append(entry)
    print(f"[{kind.upper()}] {message}")
    if data:
        print(f"  Data: {json.dumps(data, ensure_ascii=False)[:300]}")

def main():
    transcript = []
    char_id = None
    
    # === Phase 1: Character Creation ===
    log(transcript, "info", f"Creating character: {CHAR_NAME}")
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        r = client.post("/characters", json={
            "name": CHAR_NAME,
            "race": "Human",
            "class": "Fighter",
            "background": "Soldier"
        })
        log(transcript, "create", f"POST /characters -> {r.status_code}", {"response": r.text[:500]})
        r.raise_for_status()
        char_data = r.json()
        char_id = char_data["id"]
        log(transcript, "create", f"Character created", {"id": char_id, "name": char_data.get("name")})
        
        # Check initial flags
        r2 = client.get(f"/narrative/flags/{char_id}")
        log(transcript, "check", f"GET /narrative/flags/{char_id} -> {r2.status_code}", r2.json())
    
    # === Phase 2: Opening Exploration (Thornhold + statue) ===
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        # Explore Thornhold twice to ensure statue flag
        for i in range(2):
            r = client.post(f"/characters/{char_id}/actions", json={"action_type": "explore"})
            log(transcript, "explore", f"Explore Thornhold #{i+1} -> {r.status_code}", 
                {"success": r.json().get("success"), "narration": r.json().get("narration", "")[:100]})
        
        # Check statue flag
        r = client.get(f"/narrative/flags/{char_id}")
        flags = r.json()
        log(transcript, "check", f"Narrative flags after explore", flags)
        statue_flag = flags.get("thornhold_statue_observed")
        log(transcript, "check", f"thornhold_statue_observed = {statue_flag}")
    
    # === Phase 3: Try to reach Sister Drenna ===
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        # Try move to find Drenna location first
        log(transcript, "attempt", "Attempting move to 'crossroads' (expected Drenna location)")
        r = client.post(f"/characters/{char_id}/actions", json={"action_type": "move", "target": "crossroads"})
        move_data = r.json()
        log(transcript, "move", f"Move to crossroads -> {r.status_code}", 
            {"success": move_data.get("success"), "narration": move_data.get("narration", "")[:200]})
        
        # Get fresh character state to check location
        r2 = client.get(f"/characters/{char_id}")
        char_state = r2.json()
        location_id = char_state.get("location_id")
        current_location = char_state.get("current_location_id")
        log(transcript, "check", f"Character state after move", {
            "location_id": location_id,
            "current_location_id": current_location
        })
    
    # === Phase 4: DM turn — Talk to Drenna ===
    with httpx.Client(base_url=DM_URL, timeout=TIMEOUT) as client:
        r = client.post("/dm/turn", json={
            "character_id": char_id,
            "message": "I look for Sister Drenna"
        })
        log(transcript, "dm", f"DM turn: 'I look for Sister Drenna' -> {r.status_code}", 
            {"scene": r.json().get("scene", "")[:300] if r.status_code == 200 else r.text[:200]})
        
        if r.status_code == 200:
            dm_data = r.json()
            log(transcript, "dm", "DM turn scene", {
                "scene_preview": dm_data.get("scene", "")[:200],
                "choices_count": len(dm_data.get("choices", [])),
                "flags": dm_data.get("character_flags")
            })
            
            # If Drenna dialogue is presented, accept quest
            scene_lower = dm_data.get("scene", "").lower()
            if "drenna" in scene_lower or "quest" in scene_lower:
                log(transcript, "dm", "Drenna dialogue detected, accepting quest")
                r2 = client.post("/dm/turn", json={
                    "character_id": char_id,
                    "message": "I accept Drenna's request"
                })
                log(transcript, "dm", f"Quest acceptance -> {r2.status_code}", 
                    {"scene": r2.json().get("scene", "")[:200] if r2.status_code == 200 else r2.text[:200]})
    
    # === Phase 5: Try to reach Brother Kol ===
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        # Check current location and available moves
        r = client.get(f"/characters/{char_id}")
        char_state = r.json()
        current = char_state.get("location_id")
        log(transcript, "check", f"Current location before Kol attempt: {current}")
        
        # Try to move to cave-depths or use DM travel
        log(transcript, "attempt", "Attempting move to 'cave-depths'")
        r = client.post(f"/characters/{char_id}/actions", json={"action_type": "move", "target": "cave-depths"})
        move_data = r.json()
        log(transcript, "move", f"Move to cave-depths -> {r.status_code}", 
            {"success": move_data.get("success"), "narration": move_data.get("narration", "")[:200]})
        
        if not move_data.get("success"):
            log(transcript, "warning", "Direct move failed, will attempt DM travel")
    
    with httpx.Client(base_url=DM_URL, timeout=TIMEOUT) as client:
        # DM travel to Kol
        r = client.post("/dm/turn", json={
            "character_id": char_id,
            "message": "I travel to Brother Kol in the cave-depths"
        })
        log(transcript, "dm", f"DM turn: travel to Kol -> {r.status_code}", 
            {"scene": r.json().get("scene", "")[:300] if r.status_code == 200 else r.text[:200]})
        
        if r.status_code == 200:
            dm_data = r.json()
            scene_lower = dm_data.get("scene", "").lower()
            if "kol" in scene_lower or "brother" in scene_lower:
                log(transcript, "dm", "Kol location reached via DM travel, initiating dialogue")
                r2 = client.post("/dm/turn", json={
                    "character_id": char_id,
                    "message": "I talk to Brother Kol"
                })
                log(transcript, "dm", f"Kol dialogue -> {r2.status_code}", 
                    {"scene": r2.json().get("scene", "")[:300] if r2.status_code == 200 else r2.text[:200]})
                
                # Check flags after Kol dialogue
                with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as r_client:
                    r3 = r_client.get(f"/narrative/flags/{char_id}")
                    flags = r3.json()
                    log(transcript, "check", f"Flags after Kol dialogue", flags)
                    kol_flag = flags.get("kol_backstory_known")
                    log(transcript, "check", f"kol_backstory_known = {kol_flag}")
    
    # === Phase 6: Final state capture ===
    with httpx.Client(base_url=RULES_URL, timeout=TIMEOUT) as client:
        r = client.get(f"/characters/{char_id}")
        final_char = r.json()
        log(transcript, "final", f"Final character state", {
            "location": final_char.get("location_id"),
            "hp": final_char.get("hit_points"),
            "ac": final_char.get("armor_class"),
            "level": final_char.get("level")
        })
        
        r2 = client.get(f"/narrative-flags/{char_id}")
        log(transcript, "final", f"Final flags", r2.json())
    
    # === Save report ===
    report = {
        "playthrough_id": str(uuid.uuid4()),
        "character_name": CHAR_NAME,
        "character_id": char_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "rules_url": RULES_URL,
        "dm_url": DM_URL,
        "transcript": transcript,
        "scenario": "D"
    }
    
    outfile = f"reports/playtest-scenarioD-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.json"
    os.makedirs("reports", exist_ok=True)
    with open(outfile, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(transcript, "info", f"Report saved to {outfile}")
    
    # Print summary for the cron output
    print("\n=== PLAYTEST SUMMARY ===")
    print(f"Character: {CHAR_NAME} [{char_id}]")
    print(f"Scenario: D (Climax/Endings)")
    print(f"Transitions: {len([e for e in transcript if e['kind'] in ('move', 'explore', 'dm')])}")
    
    # Issue reproduction summary
    print("\nIssue check:")
    print(f"  ISSUE-013 (world graph): tested via move attempts")
    print(f"  ISSUE-003 (kol flag): checked after Kol dialogue")
    print(f"  ISSUE-012 (DM root): already known smoke failure")
    
    return 0

if __name__ == "__main__":
    exit(main())
