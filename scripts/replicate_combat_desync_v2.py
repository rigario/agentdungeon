#!/usr/bin/env python3
"""
ISSUE-015 replication v2: The event log is nested under {'events': [...]}.
We need to trigger actual combat (not just explore) and then force a defeat.
"""
import httpx, uuid, json, time

RULES = "https://agentdungeon.com"
DM = "https://agentdungeon.com"

cname = f"Desync-{uuid.uuid4().hex[:6]}"

with httpx.Client(timeout=120.0) as c:
    def get_char(cid):
        return c.get(f"{RULES}/characters/{cid}").json()

    def get_log(cid):
        resp = c.get(f"{RULES}/characters/{cid}/event-log")
        data = resp.json()
        if isinstance(data, dict) and "events" in data:
            return data["events"]
        if isinstance(data, list):
            return data
        return []

    # Create character
    resp = c.post(f"{RULES}/characters", json={
        "name": cname, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    cid = resp.json()["id"]
    print(f"Character: {cid}")

    # Move to thornhold then forest-edge
    c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "thornhold"
    })
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "forest-edge"
    })
    print(f"At forest-edge: {resp.json().get('success')}")

    # Trigger combat via DM turn
    session_id = None

    # Turn 1: look around forest
    resp = c.post(f"{DM}/dm/turn", json={
        "character_id": cid,
        "message": "I look around the Whisperwood edge, watching for threats."
    }, timeout=120.0)
    data = resp.json()
    session_id = data.get("session_id")
    trace = data.get("server_trace") or {}
    print(f"DM turn 1: endpoint={trace.get('server_endpoint_called')}")
    
    choices = data.get("choices") or []
    print(f"  Choices: {[c2.get('label') if isinstance(c2,dict) else c2 for c2 in choices[:5]]}")

    # Check if combat started
    m = data.get("mechanics") or {}
    if m.get("what_happened"):
        print(f"  Events: {m['what_happened']}")

    # Turn 2: try to fight something to trigger actual combat
    resp = c.post(f"{DM}/dm/turn", json={
        "character_id": cid,
        "message": "I attack any hostile creatures nearby with my longsword.",
        "session_id": session_id
    }, timeout=120.0)
    data = resp.json()
    trace = data.get("server_trace") or {}
    m = data.get("mechanics") or {}
    print(f"\nDM turn 2: endpoint={trace.get('server_endpoint_called')}")
    if m.get("what_happened"):
        print(f"  Events: {m['what_happened']}")
    print(f"  HP: {m.get('hp', {}).get('current', '?')}/{m.get('hp', {}).get('max', '?')}")

    char_after = get_char(cid)
    print(f"  Character HP: {char_after.get('hp_current')}/{char_after.get('hp_max')}")
    print(f"  Location: {char_after.get('location_id')}")

    # Check event log
    ev = get_log(cid)
    types = [e.get("event_type","?") for e in ev]
    print(f"\nEvent log types: {types}")
    
    combat_events = [e for e in ev if e.get("event_type","").startswith("combat")]
    for e in combat_events:
        print(f"  {e.get('event_type')}: {json.dumps(e, indent=2, default=str)[:300]}")

    # Check if dead
    has_defeat = any(e.get("event_type") == "combat_defeat" for e in ev)
    has_victory = any(e.get("event_type") == "combat_victory" for e in ev)
    hp_current = char_after.get("hp_current")
    
    print(f"\n=== DESYNC CHECK ===")
    print(f"  combat_defeat in log: {has_defeat}")
    print(f"  combat_victory in log: {has_victory}")
    print(f"  HP from GET: {hp_current}/{char_after.get('hp_max')}")
    
    if has_defeat and hp_current and hp_current > 0:
        print(f"\n❌** CONFIRMED DESYNC: event_log says combat_defeat but GET HP={hp_current} > 0")
    elif has_defeat and (hp_current is None or hp_current == 0):
        print(f"\n✅ SYNCED: combat_defeat and HP reflects defeat ({hp_current})")
    elif not has_defeat and not has_victory:
        print(f"\n⚠️  Combat still in progress or no combat triggered")
    else:
        print(f"\n✅ No desync (or combat ongoing)")
