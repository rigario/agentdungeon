#!/usr/bin/env python3
"""Combat trigger + XP verification for ISSUE-020"""

import urllib.request, urllib.error, json, datetime

RULES = "https://agentdungeon.com"
CHAR_ID = "freezeprobe-b890f6"

def POST(path, body):
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{RULES}{path}", data=data, headers={"Content-Type":"application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

def GET(path):
    try:
        req = urllib.request.Request(f"{RULES}{path}", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
print(f"\n=== ISSUE-020 Deep Dive — {now} ===\n")

# Character sheet before
print("--- Character state ---")
status, char = GET(f"/characters/{CHAR_ID}")
print(f"GET /characters/{CHAR_ID}: {status}")
if isinstance(char, dict):
    print(f"  location_id: {char.get('location_id')}")
    print(f"  public xp: {char.get('xp')}")
    sheet = char.get('sheet_json', {})
    print(f"  sheet_json keys: {list(sheet.keys())}")
    print(f"  sheet_json.xp: {sheet.get('xp','MISSING')}")
    print(f"  sheet_json.treasure: {sheet.get('treasure','MISSING')}")

# Event log endpoint exploration
print("\n--- Event log endpoint ---")
for path in [f"/event-log/{CHAR_ID}", f"/characters/{CHAR_ID}/event-log", f"/api/event-log/{CHAR_ID}"]:
    s, r = GET(path)
    r_str = str(r)
    if len(r_str) > 120:
        r_short = r_str[0:120] + "..."
    else:
        r_short = r_str
    print(f"  {path}: {s} — {r_short}")

# Trigger combat by exploring at a combat biome (forest-edge? but exits None - try anyway)
print("\n--- Try combat trigger via explore ---")
status_ex, explore = POST(f"/characters/{CHAR_ID}/actions", {"action_type":"explore"})
print(f"POST explore: {status_ex} — {str(explore)[:200]}")
if isinstance(explore, dict):
    events = explore.get('events', [])
    print(f"  events returned: {len(events)}")
    for ev in events:
        ev_type = ev.get('event_type', '?')
        details_raw = str(ev.get('details',''))
        if len(details_raw) > 100:
            details_short = details_raw[0:100] + "..."
        else:
            details_short = details_raw
        print(f"    - {ev_type}: {details_short}")

# Check DM turn to see if combat appears
print("\n--- DM turn (should show combat if any) ---")
status_dm, dm = POST(f"{RULES}/dm/turn", {"character_id": CHAR_ID, "message": "I look around."})
dm_str = str(dm)
if len(dm_str) > 200:
    dm_short = dm_str[0:200] + "..."
else:
    dm_short = dm_str
print(f"POST /dm/turn: {status_dm} — {dm_short}")

# Summary
print("\n=== End probe ===")
