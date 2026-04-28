#!/usr/bin/env python3
"""Simple state probe — avoid timeouts"""

import urllib.request, urllib.error, json, datetime

RULES = "https://agentdungeon.com"
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
        resp = urllib.request.urlopen(req, timeout=12)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read()
        try:
            return e.code, json.loads(err_body)
        except:
            return e.code, err_body[:200].decode('utf-8', errors='replace')
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
print(f"\n=== State Probe — {now} ===\n")

# Fresh character GET
status, char = GET(f"/characters/{CHAR_ID}")
print(f"GET /characters: {status}")
if isinstance(char, dict):
    print(f"  location_id: {char.get('location_id')}")
    print(f"  current_location_id: {char.get('current_location_id')}")
    print(f"  xp: {char.get('xp')}")
    sheet = char.get('sheet_json', {})
    print(f"  sheet_json type: {type(sheet).__name__}, keys: {list(sheet.keys()) if isinstance(sheet, dict) else sheet}")

# NPCs at current location
status, npcs = GET(f"/npcs/at/{char.get('location_id','rusty-tankard')}")
print(f"\n/npcs/at: {status}")
if isinstance(npcs, dict):
    for n in npcs.get('npcs', []):
        print(f"  - {n.get('name')} (id={n.get('id')})")

# Move attempt to south-road (canonical ID)
print("\n--- Move attempt ---")
status, resp = POST(f"/characters/{CHAR_ID}/actions", {"action_type":"move","target":"south-road"})
print(f"POST move south-road: {status}")
resp_str = str(resp)
if len(resp_str) > 200:
    print(f"  Response: {resp_str[0:200]}...")
else:
    print(f"  Response: {resp_str}")

# Refresh character after move
status2, char2 = GET(f"/characters/{CHAR_ID}")
print(f"GET /characters (after move): {status2}")
if isinstance(char2, dict):
    print(f"  location_id: {char2.get('location_id')}")
    print(f"  current_location_id: {char2.get('current_location_id')}")

# DM turn
print("\n--- DM turn ---")
status_dm, dm = POST(f"{RULES}/dm/turn", {"character_id": CHAR_ID, "message": "I look around."})
dm_str = str(dm)
if len(dm_str) > 200:
    print(f"POST /dm/turn: {status_dm} — {dm_str[0:200]}...")
else:
    print(f"POST /dm/turn: {status_dm} — {dm_str}")

print("\n=== Done ===\n")
