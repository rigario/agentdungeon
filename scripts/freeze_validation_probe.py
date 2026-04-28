#!/usr/bin/env python3
"""
Freeze validation probes — ISSUE-018..022
Creates evidence blocks for PLAYTEST-ISSUES.md update.
"""

import urllib.request, urllib.error, json, sys, datetime

RULES = "https://agentdungeon.com"
DM = "https://agentdungeon.com"
CHAR_ID = "freezeprobe-b890f6"

def GET(path):
    try:
        req = urllib.request.Request(f"{RULES}{path}", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

def POST(path, body):
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{RULES}{path}", data=data, headers={"Content-Type":"application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

def DM_TURN(message):
    try:
        body = json.dumps({"character_id": CHAR_ID, "message": message}).encode("utf-8")
        req = urllib.request.Request(f"{DM}/dm/turn", data=body, headers={"Content-Type":"application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=12)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

print(f"\n=== D20 FREEZE VALIDATION PROBE — {now} ===\n")

# --- ISSUE-018: DM planner NPC visibility ---
print("--- ISSUE-018: NPC context propagation ---")
status_npcs, npcs = GET(f"/npcs/at/rusty-tankard")
print(f"  /npcs/at/rusty-tankard: {status_npcs}")
if isinstance(npcs, dict) and 'npcs' in npcs:
    npc_names = [n.get('name','?') for n in npcs['npcs']]
    print(f"  NPCs present: {npc_names}")
else:
    print(f"  Response: {npcs}")

# direct interact
status_int, interact = POST(f"/characters/{CHAR_ID}/actions", {"action_type":"interact","target":"Aldric the Innkeeper"})
print(f"  direct interact Aldric: {status_int} — {str(interact)[:120]}")

# DM turn talk
status_dm, dm_resp = DM_TURN("Talk to Aldric the Innkeeper.")
print(f"  DM turn 'Talk to Aldric': {status_dm}")
if isinstance(dm_resp, dict):
    # DM response may have 'scene' or 'narration' key
    scene_text = dm_resp.get('scene') or dm_resp.get('narration') or str(dm_resp)
    scene_str = str(scene_text)
    if len(scene_str) > 200:
        scene_short = scene_str[0:200] + "..."
    else:
        scene_short = scene_str
    print(f"  Scene: {scene_short}")
    scene_lower = scene_short.lower()
    if 'aldric' in scene_lower and ('isn\'t here' in scene_lower or 'available: no one' in scene_lower or 'available:' in scene_lower):
        print("  → ISSUE-018 CONFIRMED: DM claims no one available despite NPCs present")
    else:
        print("  → DM response appears correct (needs manual review)")

# --- ISSUE-019: Natural target normalization ---
print("\n--- ISSUE-019: Target alias normalization ---")
status_dm2, dm_resp2 = DM_TURN("I go to Thornhold town square.")
print(f"  DM turn 'Thornhold town square': {status_dm2}")
if isinstance(dm_resp2, dict):
    scene_text2 = dm_resp2.get('scene') or dm_resp2.get('narration') or str(dm_resp2)
    scene_str2 = str(scene_text2)
    if len(scene_str2) > 200:
        scene2_short = scene_str2[0:200] + "..."
    else:
        scene2_short = scene_str2
    print(f"  Scene: {scene2_short}")
    scene2_lower = scene2_short.lower()
    if 'thornhold' in scene2_lower and ('location not found' in scene2_lower or 'not found' in scene2_lower):
        print("  → ISSUE-019 CONFIRMED: Raw alias forwarded instead of canonical resolve")
    else:
        print("  → Needs manual review")

# --- ISSUE-020: XP/level-up progression ---
print("\n--- ISSUE-020: XP read-model/level-up ---")
# Check current character state
status_ch, char = GET(f"/characters/{CHAR_ID}")
print(f"  GET /characters: {status_ch}")
if isinstance(char, dict):
    sheet = char.get('sheet_json', {})
    print(f"  sheet_json.xp: {sheet.get('xp','MISSING')}")
    print(f"  sheet_json.treasure.gp: {sheet.get('treasure',{}).get('gp','MISSING')}")
    print(f"  char['xp'] (public): {char.get('xp','MISSING')}")
    print(f"  hp: {char.get('hit_points',{})}")

# Check event log to see if any XP events exist
status_el, events = GET(f"/event-log/{CHAR_ID}?since=2026-04-01")
print(f"  GET /event-log: {status_el}")
if isinstance(events, dict) and 'events' in events:
    xp_events = [e for e in events['events'] if 'xp' in str(e).lower() or 'gold' in str(e).lower() or 'victory' in str(e).lower()]
    print(f"  XP/Gold events: {len(xp_events)} found")
    for ev in xp_events[-3:]:
        details_raw = str(ev.get('details', ''))
        if len(details_raw) > 100:
            details_short = details_raw[0:100] + "..."
        else:
            details_short = details_raw
        print(f"    - {ev.get('event_type')}: {details_short}")
else:
    print(f"  Events: {events}")

# Check level-up endpoint
status_lvl, lvl_resp = POST(f"/characters/{CHAR_ID}/level-up", {})
lvl_str = str(lvl_resp)
if len(lvl_str) > 120:
    lvl_short = lvl_str[0:120] + "..."
else:
    lvl_short = lvl_str
print(f"  POST /level-up: {status_lvl} — {lvl_short}")

# --- ISSUE-021: Playthrough harness state recovery ---
print("\n--- ISSUE-021: Harness recovery test ---")
print("  Running 5-turn smoke sequence to detect state corruption...")
# Simulate what the harness does: explore, move, explore, move, explore
for i, (action_type, target) in enumerate([
    ("explore", None),
    ("move", "south-road"),
    ("explore", None),
    ("move", "crossroads"),
    ("explore", None),
]):
    status, resp = POST(f"/characters/{CHAR_ID}/actions", {"action_type": action_type, "target": target} if target else {"action_type": action_type})
    if status != 200:
        resp_str = str(resp)
        if len(resp_str) > 100:
            resp_short = resp_str[0:100] + "..."
        else:
            resp_short = resp_str
        print(f"  Step {i+1} {action_type} {target or ''}: {status} — {resp_short}")
        print(f"  → ISSUE-021: Action failure detected; harness may not handle gracefully")
        break
    state = resp.get('character_state', {})
    print(f"  Step {i+1} {action_type}: success={resp.get('success', '?')}, loc={state.get('location_id')}, hp={state.get('hit_points',{}).get('current')}")
    # Check if state is invalid (deceased, None location, etc.)
    if state.get('hit_points',{}).get('current', 999) <= 0:
        print(f"  → Character deceased at step {i+1}; ISSUE-021 recovery needed")
        break
    if not state.get('location_id'):
        print(f"  → location_id None at step {i+1}; ISSUE-021 state corruption")
        break
else:
    print("  → 5 steps completed without corruption detected (manual review needed)")

# --- ISSUE-022: Safe validation route / encounter balance ---
print("\n--- ISSUE-022: Safe route / encounter balance ---")
# Check world topology
status_map, map_data = GET("/api/map/data")
print(f"  /api/map/data: {status_map}")
if isinstance(map_data, dict):
    locs = map_data.get('locations', [])
    print(f"  Total locations: {len(locs)}")
    # Check exits field for key nodes
    for loc_id in ['rusty-tankard', 'south-road', 'forest-edge', 'crossroads', 'thornhold']:
        found = next((l for l in locs if l.get('id') == loc_id), None)
        if found:
            exits = found.get('exits')
            print(f"  {loc_id}: exits={exits}")
        else:
            print(f"  {loc_id}: MISSING from world")
    # Try to chart a safe path: rusty-tankard -> south-road -> ... checking each
    print("  Checking connectivity from rusty-tankard:")
    rt = next((l for l in locs if l.get('id') == 'rusty-tankard'), None)
    if rt and rt.get('exits'):
        print(f"    Available from rusty-tankard: {list(rt['exits'].keys())}")
    else:
        print("    → No exits data; movement may rely on fallback")

# --- Cadence state ---
print("\n--- Cadence tick state ---")
status_cad, cad = GET("/cadence/status")
print(f"  /cadence/status: {status_cad}")
if isinstance(cad, dict):
    print(f"  Mode: {cad.get('config',{}).get('cadence_mode')}, Interval: {cad.get('config',{}).get('tick_interval_seconds')}s")
# Check doom clock
status_doom, doom = GET(f"/cadence/doom/{CHAR_ID}")
print(f"  /cadence/doom/{CHAR_ID}: {status_doom} — {str(doom)[:120]}")

print("\n=== Probe complete ===\n")
