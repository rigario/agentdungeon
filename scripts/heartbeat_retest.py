#!/usr/bin/env python3
"""
D20 Playtest Heartbeat - Freeze Blocker Retest
Tests ISSUE-018, ISSUE-019, ISSUE-020, and harness run for ISSUE-021/022
"""

import urllib.request, json, sys, datetime, os, subprocess

RULES_URL = "https://agentdungeon.com"
DM_URL = "https://agentdungeon.com"
now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')

def post_json(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST', headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)

def get_json(url):
    req = urllib.request.Request(url, method='GET')
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)

def create_character(name):
    status, data = post_json(RULES_URL + "/characters", {
        "name": name,
        "race": "Human",
        "class": "Fighter",
        "background": "Soldier"
    })
    if status == 201:
        return data['id']
    raise Exception(f"Character creation failed: {status} {data}")

def delete_character(char_id):
    status, _ = post_json(RULES_URL + f"/characters/{char_id}/delete", {})
    return status

# ==================== ISSUE-018: NPC Context Propagation ====================
print(f"\n{'='*80}")
print(f"ISSUE-018 Re-Test — NPC Context Propagation @ {ts}")
print(f"{'='*80}")

char_id = create_character(f"ISSUE018-{int(now.timestamp())}")
print(f"Character: {char_id} at {get_json(RULES_URL + f'/characters/{char_id}')[1].get('location_id')}")

# 1. Check NPCs at rusty-tankard
status, npc_data = get_json(RULES_URL + "/npcs/at/rusty-tankard")
npc_names = []
if status == 200 and isinstance(npc_data, dict):
    npc_names = [n.get('name', n.get('id')) for n in npc_data.get('npcs', [])]
print(f"/npcs/at/rusty-tankard: {status} → {npc_names}")

# 2. Direct interact
status, interact = post_json(RULES_URL + f"/characters/{char_id}/actions", {
    "action_type": "interact",
    "target": "Aldric the Innkeeper"
})
interact_excerpt = json.dumps(interact)[:300]
print(f"Direct interact: {status} → {interact_excerpt}")

# 3. DM turn "Talk to Aldric the Innkeeper."
status, dm_resp = post_json(DM_URL + "/dm/turn", {
    "character_id": char_id,
    "message": "Talk to Aldric the Innkeeper."
})
dm_scene = ""
intent_target = ""
if isinstance(dm_resp, dict):
    scene = dm_resp.get('scene', {})
    dm_scene = scene.get('scene', str(scene))[:300] if isinstance(scene, dict) else str(scene)[:300]
    intent = dm_resp.get('server_trace', {}).get('intent_used', {})
    intent_target = intent.get('target', '')
print(f"DM turn: {status} → scene: {dm_scene}")
print(f"  intent_used.target: {intent_target}")

delete_character(char_id)

# ==================== ISSUE-019: Natural Target Normalization ====================
print(f"\n{'='*80}")
print(f"ISSUE-019 Re-Test — Natural Target Normalization @ {ts}")
print(f"{'='*80}")

char_id = create_character(f"ISSUE019-{int(now.timestamp())}")
print(f"Character: {char_id}")

# Test A: DM turn "I go to Thornhold town square."
status, dm1 = post_json(DM_URL + "/dm/turn", {
    "character_id": char_id,
    "message": "I go to Thornhold town square."
})
dm1_scene = ""
if isinstance(dm1, dict):
    scene = dm1.get('scene', {})
    dm1_scene = scene.get('scene', str(scene))[:300] if isinstance(scene, dict) else str(scene)[:300]
print(f"DM 'Thornhold town square': {status} → {dm1_scene}")

# Test B: Direct move to canonical "thornhold"
status, move = post_json(RULES_URL + f"/characters/{char_id}/actions", {
    "action_type": "move",
    "target": "thornhold"
})
move_excerpt = json.dumps(move)[:300]
print(f"Direct move to 'thornhold': {status} → {move_excerpt}")

# Test C: DM turn "I talk to Sister Drenna."
status, dm2 = post_json(DM_URL + "/dm/turn", {
    "character_id": char_id,
    "message": "I talk to Sister Drenna."
})
dm2_scene = ""
intent_target2 = ""
if isinstance(dm2, dict):
    scene = dm2.get('scene', {})
    dm2_scene = scene.get('scene', str(scene))[:300] if isinstance(scene, dict) else str(scene)[:300]
    intent = dm2.get('server_trace', {}).get('intent_used', {})
    intent_target2 = intent.get('target', '')
print(f"DM 'Sister Drenna': {status} → {dm2_scene}")
print(f"  intent_used.target: {intent_target2}")

delete_character(char_id)

# ==================== ISSUE-020: XP/Gold/Level-Up Progression ====================
print(f"\n{'='*80}")
print(f"ISSUE-020 Re-Test — XP/Gold/Level-Up Progression @ {ts}")
print(f"{'='*80}")

char_id = create_character(f"ISSUE020-{int(now.timestamp())}")
print(f"Character: {char_id}")

# Initial state
status, initial = get_json(RULES_URL + f"/characters/{char_id}")
init_xp = initial.get('xp', 'N/A') if isinstance(initial, dict) else 'N/A'
init_gold = initial.get('gold', 'N/A') if isinstance(initial, dict) else 'N/A'
init_level = initial.get('level', 'N/A') if isinstance(initial, dict) else 'N/A'
print(f"Initial state: XP={init_xp}, Gold={init_gold}, Level={init_level}")

# Move to south-road (combat zone)
status, move_resp = post_json(RULES_URL + f"/characters/{char_id}/actions", {
    "action_type": "move",
    "target": "south-road"
})
print(f"Move to south-road: {status}")

# Explore to trigger combat
status, explore_resp = post_json(RULES_URL + f"/characters/{char_id}/actions", {
    "action_type": "explore"
})
print(f"Explore: {status}")
combat_started = False
if isinstance(explore_resp, dict):
    combat = explore_resp.get('combat', {})
    if combat and combat.get('enemy'):
        combat_started = True
        print(f"  Combat encounter: {combat.get('enemy', 'unknown')}")
        # Simulate attack via DM turn
        status, dm_resp = post_json(DM_URL + "/dm/turn", {
            "character_id": char_id,
            "message": "I attack the goblin with my longsword."
        })
        print(f"  DM turn (attack): {status}")
        if isinstance(dm_resp, dict):
            print(f"    Narration: {dm_resp.get('scene', {}).get('scene', '')[:200]}")
        
        # Check character state post-combat
        status, char_post = get_json(RULES_URL + f"/characters/{char_id}")
        if isinstance(char_post, dict):
            xp_after = char_post.get('xp', 'N/A')
            gold_after = char_post.get('gold', 'N/A')
            level_after = char_post.get('level', 'N/A')
            print(f"  Post-combat: XP={xp_after}, Gold={gold_after}, Level={level_after}")
            xp_gained = None
            if isinstance(initial, dict) and isinstance(char_post, dict):
                try:
                    xp_gained = char_post.get('xp', 0) - initial.get('xp', 0)
                except:
                    pass
            print(f"  XP gained: {xp_gained}")
        
        # Check event log
        status, events = get_json(RULES_URL + f"/events?character_id={char_id}&limit=10")
        if status == 200 and isinstance(events, dict):
            xp_events = [e for e in events.get('events', []) if e.get('event_type') in ('xp_gained', 'gold_received', 'level_up')]
            print(f"  Relevant events: {json.dumps(xp_events)}")
        
        # Check portal state
        status, portal = get_json(RULES_URL + f"/portal/{char_id}/state")
        if status == 200 and isinstance(portal, dict):
            print(f"  Portal: XP={portal.get('xp')}, Gold={portal.get('gold')}, Level={portal.get('level')}")
            print(f"  level_up_available: {portal.get('level_up_available')}")
    else:
        print(f"  No combat triggered. Explore response: {json.dumps(explore_resp)[:200]}")

delete_character(char_id)

# ==================== ISSUE-021/022: Full Harness Run ====================
print(f"\n{'='*80}")
print(f"ISSUE-021/022 — Full Playthrough Harness (First Invalid-State Detection) @ {ts}")
print(f"{'='*80}")

harness_path = "/home/rigario/Projects/rigario-d20/scripts/full_playthrough_with_gates.py"
if os.path.exists(harness_path):
    print(f"Running harness with CONTINUE=1...")
    result = subprocess.run(
        ["python3", harness_path],
        env={
            "CONTINUE": "1",
            "D20_RULES_URL": RULES_URL,
            "DM_URL": DM_URL,
            "PATH": os.environ.get('PATH', ''),
        },
        capture_output=True, text=True, timeout=120
    )
    print(f"Exit code: {result.returncode}")
    if result.stdout:
        print(f"Stdout (tail):\n{result.stdout[-800:]}")
    if result.stderr:
        print(f"Stderr (tail):\n{result.stderr[-800:]}")
else:
    print(f"ERROR: Harness not found at {harness_path}")

print(f"\n{'='*80}")
print(f"Heartbeat retest complete @ {ts}")
print(f"{'='*80}")
