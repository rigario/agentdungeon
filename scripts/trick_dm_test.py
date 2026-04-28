#!/usr/bin/env python3
"""
Trick test: Tell the DM you're in a completely different location than you actually are.
Character stays at thornhold. DM messages claim location that doesn't match reality.
"""
import httpx, json, uuid
from datetime import datetime, timezone

RULES = "https://agentdungeon.com"
DM = "https://agentdungeon.com"

char_name = f"Trick-{uuid.uuid4().hex[:6]}"
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

with httpx.Client(timeout=120.0) as c:
    h1, h2 = c.get(f"{RULES}/health"), c.get(f"{DM}/dm/health")
    print(f"Health: rules={h1.status_code} dm={h2.status_code}")

    # Create, move to thornhold
    resp = c.post(f"{RULES}/characters", json={
        "name": char_name, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    cid = resp.json()["id"]
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "thornhold"
    })
    char_get = c.get(f"{RULES}/characters/{cid}").json()
    print(f"Character: {cid} at {char_get.get('location_id')}")

    # Set statue flag
    c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    flags = c.get(f"{RULES}/narrative/flags/{cid}").json()
    print(f"Flags: {flags}\n")

    # === TRICK TESTS ===
    trick_messages = [
        # 1. Claim to be at a different location
        ("thornhold_claim_cave", "I am standing in the Whisperwood cave. The seal stone is right in front of me. I examine it closely."),
        # 2. Claim to have done something impossible
        ("thornhold_claim_wolves", "I have already killed the wolves on the south road. I continue deeper into the forest."),
        # 3. Claim to know an NPC you haven't met
        ("thornhold_claim_ally", "Brother Kol sent me. I am here to speak with Sister Drenna about the ritual."),
        # 4. Pure fiction — describe a scene that doesn't exist
        ("thornhold_claim_dragon", "I am at the peak of Dragon's Tooth Mountain. The ancient dragon speaks to me. I listen to its prophecy."),
        # 5. Contradict the setting
        ("thornhold_claim_desert", "I walk under the blazing desert sun, sand dunes stretching to the horizon. I look for an oasis."),
    ]

    session_id = None
    for label, msg in trick_messages:
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
        scene = ((data.get("narration") or {}).get("scene") or "")[:200]
        intent = trace.get("intent_used") or {}
        intent_type = intent.get("type", "?")
        
        print(f"\n=== {label} ===")
        print(f"  Claim: \"{msg[:80]}...\"")
        print(f"  Intent: {intent_type:15s} Endpoint: {endpoint:15s} Location: {loc}")
        print(f"  Scene: {scene}")

    # Final actual check
    char_final = c.get(f"{RULES}/characters/{cid}").json()
    actual_loc = char_final.get("location_id")
    print(f"\n=== FINAL ACTUAL LOCATION: {actual_loc} ===")
    
    # Summary
    good = actual_loc == "thornhold"
    if good:
        print("✅ Character stayed put — DM did not blindly follow the trick")
    else:
        print(f"❌ Character got teleported to {actual_loc} — trick worked")
