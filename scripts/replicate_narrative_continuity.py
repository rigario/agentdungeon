#!/usr/bin/env python3
"""
Replication script for DM narrative continuity bug.
Hypothesis: DM turn 2+ misroutes to `turn/start` (rules engine travel) 
instead of `actions` (in-place narrative), teleporting the character away.
"""
import httpx, json, uuid, sys
from datetime import datetime, timezone

RULES = "https://d20.holocronlabs.ai"
DM = "https://d20.holocronlabs.ai"

def check(msg: str, data: dict) -> str:
    """Extract a short label from response data."""
    trace = data.get("server_trace") or {}
    endpoint = trace.get("server_endpoint_called", "?")
    mechanics = data.get("mechanics") or {}
    loc = mechanics.get("location") or "?"
    scene = ((data.get("narration") or {}).get("scene") or "")[:120]
    return f"endpoint={endpoint} location={loc} scene=\"{scene}\""

char_name = f"NarrBug-{uuid.uuid4().hex[:6]}"
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

with httpx.Client(timeout=120.0) as c:
    # Health
    h1, h2 = c.get(f"{RULES}/health"), c.get(f"{DM}/dm/health")
    assert h1.status_code == 200 and h2.status_code == 200, f"Health: {h1.status_code} {h2.status_code}"
    print(f"[OK] Health: rules={h1.status_code} dm={h2.status_code}")

    # Create character
    resp = c.post(f"{RULES}/characters", json={
        "name": char_name, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    char = resp.json()
    cid = char["id"]
    start_loc = char.get("location_id")
    print(f"[OK] Created {cid} at {start_loc}")

    # Move to thornhold town
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "thornhold"
    })
    data = resp.json()
    char_state = data.get("character_state") or {}
    loc = char_state.get("location_id") or "?"
    success = data.get("success")
    print(f"[OK] Move to thornhold: success={success} location={loc}")

    # Verify location
    char_get = c.get(f"{RULES}/characters/{cid}").json()
    print(f"[OK] GET location_id={char_get.get('location_id')} current_location_id={char_get.get('current_location_id')}\n")

    # Explore to set statue flag
    c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    flags = c.get(f"{RULES}/narrative/flags/{cid}").json()
    print(f"[OK] Explore: flags={flags}\n")

    # === CRITICAL TEST: 4 DM turns that should all stay in thornhold ===
    session_id = None
    messages = [
        "I look around Thornhold's town square. What do I notice?",
        "I examine the old stone statue in the town square. What details do I notice?",
        "I run my hand over the stone hand looking for seal markings or sigils.",
        "I talk to Marta the Merchant about what's been happening in town.",
    ]

    results = []
    for i, msg in enumerate(messages, 1):
        body = {"character_id": cid, "message": msg}
        if session_id:
            body["session_id"] = session_id
        resp = c.post(f"{DM}/dm/turn", json=body, timeout=120)
        data = resp.json()
        session_id = data.get("session_id", session_id)
        
        trace = data.get("server_trace") or {}
        endpoint = trace.get("server_endpoint_called", "?")
        mechanics = data.get("mechanics") or {}
        loc = mechanics.get("location") or (trace.get("decision_point") or {}).get("location") or "?"
        scene = ((data.get("narration") or {}).get("scene") or "")[:150]
        intent = trace.get("intent_used") or {}
        intent_type = intent.get("type", "?")
        choices = data.get("choices") or []
        turn_id = trace.get("turn_id", "?")
        
        result = {
            "turn": i, "status": resp.status_code, "session": session_id,
            "endpoint": endpoint, "location_mechanics": loc,
            "intent_type": intent_type, "turn_id": turn_id,
            "has_choices": len(choices) > 0,
            "scene_preview": scene,
        }
        results.append(result)
        
        print(f"DM Turn {i}:")
        print(f"  Message: \"{msg}\"")
        print(f"  Status={resp.status_code} Session={session_id}")
        print(f"  Endpoint={endpoint}  Intent={intent_type}  TurnID={turn_id}")
        print(f"  Location(mechanics)={loc}")
        print(f"  Scene: {scene}...")
        print()

    # Verify final actual location
    char_final = c.get(f"{RULES}/characters/{cid}").json()
    actual_loc = char_final.get("location_id")
    print(f"\n[VERIFY] Final actual location: {actual_loc}")
    
    # Determine pass/fail
    fails = []
    for r in results:
        if r["location_mechanics"] not in ("thornhold", "rusty-tankard") and r["location_mechanics"] != "?":
            fails.append(f"Turn {r['turn']}: teleported to {r['location_mechanics']} via {r['endpoint']} (intent={r['intent_type']})")
    
    print(f"\n=== RESULTS ===")
    if fails:
        print(f"❌ BUG CONFIRMED — {len(fails)} continuity breaks:")
        for f in fails:
            print(f"  • {f}")
        print(f"  Final location: {actual_loc} (should be thornhold)")
    else:
        print(f"✅ BUG NOT REPRODUCED — all turns stayed in thornhold")
    
    # Print structured evidence
    print(f"\n=== EVIDENCE BLOCK ===")
    print(f"Character: {cid}")
    print(f"Timestamp: {ts}")
    for r in results:
        print(f"Turn {r['turn']}: {r['endpoint']:20s} intent={r['intent_type']:15s} loc={r['location_mechanics']:15s} choices={r['has_choices']}")
    
    sys.exit(1 if fails else 0)
