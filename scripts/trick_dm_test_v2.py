#!/usr/bin/env python3
"""
Trick test v2 — capture full location trajectory per turn.
Character starts at thornhold. We send 5 trick messages claiming
to be elsewhere. Log actual location BEFORE and AFTER each turn.
"""
import httpx, json, uuid
from datetime import datetime, timezone

RULES = "https://d20.holocronlabs.ai"
DM = "https://d20.holocronlabs.ai"

char_name = f"Trick2-{uuid.uuid4().hex[:6]}"
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

with httpx.Client(timeout=120.0) as c:
    def loc(cid):
        """Get current character location."""
        ch = c.get(f"{RULES}/characters/{cid}").json()
        return ch.get("location_id")

    def explore_setup(cid):
        """Explore to ensure flag set."""
        c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})

    # Create + move to thornhold
    resp = c.post(f"{RULES}/characters", json={
        "name": char_name, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    cid = resp.json()["id"]
    c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "move", "target": "thornhold"})
    explore_setup(cid)

    print(f"Character: {cid}")
    print(f"Start location: {loc(cid)}\n")

    # Trick messages — each starts after a fresh explore to reset narrative state
    tricks = [
        ("Claim: cave-depths", "I am standing in the Whisperwood cave. The seal stone is right in front of me."),
        ("Claim: south road + wolves dead", "I have already killed the wolves on the south road. I continue deeper into the forest."),
        ("Claim: Brother Kol sent me", "Brother Kol sent me. I must speak with Sister Drenna about the ritual."),
        ("Claim: Dragon's Tooth Mountain", "I am at the peak of Dragon's Tooth Mountain, speaking with an ancient dragon."),
        ("Claim: in a desert", "I walk under the blazing desert sun, looking for an oasis."),
        ("Claim: I'm in Waterdeep", "I walk through the streets of Waterdeep, looking for the Yawning Portal inn."),
        ("Claim: I'm in Baldur's Gate", "I'm in Baldur's Gate and I need to find the Flaming Fist headquarters."),
        ("Claim: I just came from a tavern", "I just left the tavern. I'm heading to the crossroads meeting."),
    ]

    session_id = None
    for label, msg in tricks:
        before = loc(cid)
        body = {"character_id": cid, "message": msg}
        if session_id:
            body["session_id"] = session_id
        resp = c.post(f"{DM}/dm/turn", json=body, timeout=120)
        data = resp.json()
        session_id = data.get("session_id", session_id)

        trace = data.get("server_trace") or {}
        endpoint = trace.get("server_endpoint_called", "?")
        mechanics = data.get("mechanics") or {}
        m_loc = mechanics.get("location", "?")
        scene = ((data.get("narration") or {}).get("scene") or "")[:120]
        intent = (trace.get("intent_used") or {}).get("type", "?")

        after = loc(cid)
        teleported = after != before
        marker = "🔴 TELEPORTED" if teleported else "✅ STAYED"

        print(f"{marker} | {label}")
        print(f"       intent={intent:15s} endpoint={endpoint:15s} before={before:15s} after={after:15s} mech_loc={m_loc}")
        print(f"       scene: {scene}")
        print()

    print(f"=== FINAL: {loc(cid)} ===")
