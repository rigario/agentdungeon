#!/usr/bin/env python3
"""
ISSUE-015 replication v3: Use direct API actions to trigger combat,
bypassing the DM agent's teleportation bug (ISSUE-016).
"""
import httpx, uuid, json, time

RULES = "https://d20.holocronlabs.ai"

cname = f"Desync-{uuid.uuid4().hex[:6]}"

with httpx.Client(timeout=60.0) as c:
    def get_char(cid):
        ch = c.get(f"{RULES}/characters/{cid}").json()
        return ch

    def get_log(cid):
        resp = c.get(f"{RULES}/characters/{cid}/event-log")
        data = resp.json()
        if isinstance(data, dict) and "events" in data:
            return data["events"]
        return data if isinstance(data, list) else []

    # Create character
    resp = c.post(f"{RULES}/characters", json={
        "name": cname, "race": "Human", "class": "Fighter", "background": "Soldier"
    })
    cid = resp.json()["id"]
    print(f"Character: {cid}")

    # Move to thornhold -> forest-edge
    c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "move", "target": "thornhold"})
    print(f"Moved to thornhold")

    resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "move", "target": "forest-edge"})
    data = resp.json()
    print(f"Moved to forest-edge: success={data.get('success')} location={get_char(cid).get('location_id')}")

    # Explore at forest-edge
    print(f"\n--- Exploring at forest-edge ---")
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    data = resp.json()
    print(f"Explore: success={data.get('success')}")
    print(f"  narration: {data.get('narration','')[:200]}")
    
    combat = data.get("combat")
    if combat:
        print(f"  🎮 Combat triggered!")
        enemies = combat.get("enemies", [])
        for e in enemies:
            print(f"    Enemy: {e.get('type','?')} hp={e.get('hit_points','?')}")
        combat_id = combat.get("combat_id") or data.get("combat_id")
        print(f"  combat_id: {combat_id}")
    else:
        print(f"  No combat from explore (combat field: {combat})")
        # Try explore again
        print(f"\n--- Second explore attempt ---")
        resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
        data = resp.json()
        combat = data.get("combat")
        print(f"Explore 2: success={data.get('success')} combat={'present' if combat else 'none'}")
        if combat:
            enemies = combat.get("enemies", [])
            combat_id = combat.get("combat_id")
            for e in enemies:
                print(f"    Enemy: {e.get('type','?')} hp={e.get('hit_points','?')}")
    
    # If combat active, get state
    if combat_id:
        print(f"\n--- Combat state ---")
        resp = c.get(f"{RULES}/characters/{cid}/combat")
        print(f"  GET combat: status={resp.status_code}")
        if resp.status_code == 200:
            cs = resp.json()
            print(f"  Enemies: {[(e['type'], e.get('hit_points','?')) for e in cs.get('enemies',[])]}")
            print(f"  Round: {cs.get('round')}")
            print(f"  Your turn: {cs.get('is_your_turn')}")
        
        # Hit each enemy until dead
        print(f"\n--- Attacking enemies ---")
        enemies = cs.get("enemies", [])
        for i, e in enumerate(enemies):
            for hit in range(5):  # max 5 hits per enemy
                resp = c.post(f"{RULES}/characters/{cid}/combat/act", json={
                    "action": "attack", "target_index": i, "d20_roll": 20
                })
                r = resp.json()
                e_new = r.get("enemies", [])
                if e_new:
                    print(f"  Hit enemy {i} (round {r.get('round')}): enemy HP now {e_new[i].get('hit_points','?')}")
                if r.get("combat_over"):
                    print(f"  🏁 Combat over! Result: {r.get('result')}")
                    # Record HP after defeat
                    char_after = get_char(cid)
                    print(f"  HP after combat: {char_after.get('hp_current')}/{char_after.get('hp_max')}")
                    break
            if r.get("combat_over"):
                break

    # Check event log
    ev = get_log(cid)
    types = [e.get("event_type","?") for e in ev]
    print(f"\n--- Event log ---")
    print(f"Types: {types}")
    
    for e in ev:
        if e.get("event_type","").startswith("combat") or e.get("event_type") in ("move", "explore"):
            print(f"  {e.get('event_type'):20s} loc={e.get('location_id','?'):15s} desc={str(e.get('description',''))[:100]}")

    # Final state
    print(f"\n--- Final state ---")
    char_final = get_char(cid)
    print(f"  HP: {char_final.get('hp_current')}/{char_final.get('hp_max')}")
    print(f"  Location: {char_final.get('location_id')}")
    print(f"  Conditions: {char_final.get('conditions', {})}")

    # Try action
    resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
    print(f"  Post-combat action: status={resp.status_code}")
    if resp.status_code == 403:
        print(f"  ❌ BLOCKED: {resp.text[:200]}")

    # Desync check
    has_defeat = any(e.get("event_type") == "combat_defeat" for e in ev)
    has_victory = any(e.get("event_type") == "combat_victory" for e in ev)
    hp_cur = char_final.get("hp_current")
    
    print(f"\n=== ISSUE-015 DESYNC CHECK ===")
    if has_defeat:
        if hp_cur and hp_cur > 0:
            print(f"❌ DESYNC CONFIRMED: combat_defeat in log but GET HP={hp_cur} > 0")
        else:
            print(f"✅ SYNCED: combat_defeat and HP reflects ({hp_cur})")
    elif has_victory:
        print(f"🟢 Combat victory, no desync applicable")
    else:
        print(f"⚠️  No combat defeat detected (encounter may not have triggered)")
