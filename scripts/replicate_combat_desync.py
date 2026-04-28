#!/usr/bin/env python3
"""
Replication script for ISSUE-015: Character state desync after combat defeat.
1. Create character at forest-edge (where combat encounter triggers)
2. Trigger combat via explore
3. Get defeated in combat
4. Check event_log for combat_defeat
5. Check GET /characters/{id} for HP
6. Check if POST actions gives 403 character_deceased
"""
import httpx, uuid, json, time, sys, os
from datetime import datetime, timezone

RULES = "https://agentdungeon.com"

cname = f"Desync-{uuid.uuid4().hex[:6]}"
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

with httpx.Client(timeout=60.0) as c:
    def get_char(cid):
        return c.get(f"{RULES}/characters/{cid}").json()

    def get_flags(cid):
        return c.get(f"{RULES}/narrative/flags/{cid}").json()

    def get_event_log(cid):
        return c.get(f"{RULES}/characters/{cid}/event-log").json()

    # 1. Create character
    resp = c.post(f"{RULES}/characters", json={
        "name": cname, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    cid = resp.json()["id"]
    start_loc = get_char(cid).get("location_id")
    print(f"Character: {cid} at {start_loc}")

    # 2. Move from rusty-tankard -> thornhold
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "thornhold"
    })
    print(f"Move to thornhold: {resp.json().get('success')}")

    # 3. Move to forest-edge (combat zone)
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={
        "action_type": "move", "target": "forest-edge"
    })
    print(f"Move to forest-edge: {resp.json().get('success')}")

    # 4. Explore to trigger combat
    print("\n--- Triggering combat via explore ---")
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    data = resp.json()
    print(f"Explore: success={data.get('success')} narration={data.get('narration','')[:200]}")
    combat = data.get("combat", {})
    if combat:
        enemies = combat.get("enemies", [])
        print(f"Combat triggered! Enemies: {[(e['type'], e.get('id','?')) for e in enemies]}")
    else:
        # Try DM turn to trigger combat
        print("No combat from explore, trying DM turn...")
        resp = c.post(f"https://agentdungeon.com/dm/turn", json={
            "character_id": cid,
            "message": "I search for danger in the forest."
        }, timeout=60.0)
        data = resp.json()
        print(f"DM turn: endpoint={(data.get('server_trace') or {}).get('server_endpoint_called')}")
        choices = data.get("choices", [])
        print(f"Choices: {[c.get('label',c) if isinstance(c,dict) else c for c in choices[:5]]}")

    # 5. Check event log
    print(f"\n--- Event log ---")
    ev = get_event_log(cid)
    types = [e.get("event_type","?") for e in ev]
    print(f"Event types: {types}")
    for e in ev:
        if e.get("event_type") in ("combat_start", "combat_round", "combat_defeat", "combat_victory"):
            print(f"  {e.get('event_type')}: {json.dumps({k:v for k,v in e.items() if k!='event_type'}, default=str)[:200]}")

    # 6. Final character state
    print(f"\n--- Character state ---")
    char = get_char(cid)
    print(f"  location_id={char.get('location_id')}")
    print(f"  current_location_id={char.get('current_location_id')}")
    print(f"  HP: {char.get('hp_current')}/{char.get('hp_max')}")
    print(f"  conditions: {char.get('conditions', {})}")

    # 7. Try an action to see if it's blocked
    print(f"\n--- Action test ---")
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    print(f"  explore: status={resp.status_code}")
    if resp.status_code == 403:
        print(f"  👹 BLOCKED: {resp.text[:200]}")
    elif resp.status_code == 200:
        print(f"  ✅ OK: {resp.json().get('narration','')[:100]}")

    # 8. Summary
    print(f"\n=== DESYNC CHECK ===")
    has_defeat = any(e.get("event_type") == "combat_defeat" for e in ev)
    has_victory = any(e.get("event_type") == "combat_victory" for e in ev)
    hp_ok = char.get("hp_current") and char.get("hp_current", 0) > 0
    blocked = resp.status_code == 403
    
    if has_defeat and hp_ok:
        print(f"❌ DESYNC CONFIRMED: event_log says combat_defeat but GET HP={char.get('hp_current')}/{char.get('hp_max')}")
    elif has_defeat and not hp_ok:
        print(f"✅ SYNCED: combat_defeat in log AND HP reflects it ({char.get('hp_current')}/{char.get('hp_max')})")
    elif has_victory and blocked:
        print(f"⚠️  POSSIBLE DESYNC: combat_victory but action blocked (403)")
    elif not has_defeat and not has_victory:
        print(f"⚠️  No combat occurred (no encounter triggered at forest-edge)")
    else:
        print(f"✅ No desync detected")
