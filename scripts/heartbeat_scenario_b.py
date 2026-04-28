#!/usr/bin/env python3
"""
D20 Heartbeat — Scenario B (Absurd/AI Stress Test)
Run: python scripts/heartbeat_scenario_b.py
"""

import os, json, datetime, subprocess, sys
import requests

RULES_URL = os.environ.get("D20_RULES_URL", "https://agentdungeon.com")
DM_URL = os.environ.get("DM_URL", "https://agentdungeon.com")

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

def now_ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def log(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(data, indent=2) + "\n")

# Create run dir
run_id = f"heartbeat-b-{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}"
run_dir = os.path.join('playtest-runs', run_id)
os.makedirs(run_dir, exist_ok=True)

transcript = []
prose_lines = []

def record(kind, message, data=None):
    entry = {"timestamp": now_ts(), "kind": kind, "message": message, "data": data or {}}
    transcript.append(entry)
    # Also append to prose log
    prose_lines.append(f"[{now_ts()}] {kind.upper()}: {message}")
    if data:
        prose_lines.append(f"  Data: {json.dumps(data, ensure_ascii=False)[:500]}")

# 1. Character creation
print("1. Creating character...")
resp = session.post(f"{RULES_URL}/characters", json={
    "name": f"HbB-{datetime.datetime.now().strftime('%Y%m%d%H%M')}",
    "race": "Human",
    "class": "Fighter",
    "background": "Soldier"
})
assert resp.status_code == 201, f"Char create failed: {resp.status_code} {resp.text}"
char_id = resp.json()["id"]
record("create", f"Character created: {char_id}", {"rules_url": RULES_URL})
print(f"   Created {char_id}")

# Save initial state
r = session.get(f"{RULES_URL}/characters/{char_id}")
assert r.status_code == 200
initial = r.json()
record("fetch_initial", "Initial character state", {
    "location_id": initial.get("location_id"),
    "current_location_id": initial.get("current_location_id")
})
prose_lines.append(f"Initial location: {initial.get('location_id')}")

# 2. Move to thornhold (test persistence ISSUE-007)
print("2. Moving to thornhold...")
r = session.post(f"{RULES_URL}/characters/{char_id}/actions",
                 json={"action_type": "move", "target": "thornhold"})
assert r.status_code == 200, f"Move failed: {r.status_code}"
move_data = r.json()
record("move", "Move to thornhold", {
    "success": move_data.get("success"),
    "character_state": move_data.get("character_state", {}),
    "server_trace": move_data.get("server_trace", {})
})

# Verify via GET
r2 = session.get(f"{RULES_URL}/characters/{char_id}")
char_get = r2.json()
loc_id = char_get.get("location_id")
cur_id = char_get.get("current_location_id")
record("verify", f"After move — location_id={loc_id}, current_location_id={cur_id}", {
    "location_id": loc_id,
    "current_location_id": cur_id
})
prose_lines.append(f"Post-move: location_id={loc_id}, current_location_id={cur_id}")

# 3. DM turn — Absurd intent 1: swallow statue
print("3. DM turn — absurd intent: 'I swallow the statue'")
dm_msg = "I swallow the statue whole."
r = session.post(f"{DM_URL}/dm/turn",
                 json={"character_id": char_id, "message": dm_msg})
assert r.status_code == 200, f"DM turn failed: {r.status_code}"
dm_data = r.json()
narration = dm_data.get("narration", {})
scene = narration.get("scene", "")
choices = dm_data.get("choices", [])
intent = dm_data.get("server_trace", {}).get("intent_used", {})
loc_after = dm_data.get("character_state", {}).get("location_id")
record("dm_turn", "Absurd: swallow statue", {
    "intent_type": intent.get("type"),
    "intent_target": intent.get("target"),
    "location_after": loc_after,
    "choices": [c.get("label") for c in choices],
    "scene_preview": scene[:200]
})
prose_lines.append(f"DM intent: {intent.get('type')} / {intent.get('target')}")
prose_lines.append(f"Location after: {loc_after}")
prose_lines.append(f"Scene: {scene[:300]}")
# Save full DM prose
dm_prose_path = os.path.join(run_dir, 'dm-prose.md')
with open(dm_prose_path, 'a') as f:
    f.write(f"\n## DM Turn — 'I swallow the statue'\n")
    f.write(f"Timestamp: {now_ts()}\n")
    f.write(f"Intent: {json.dumps(intent, indent=2)}\n")
    f.write(f"Scene:\n{scene}\n\n")
    f.write(f"Choices:\n{json.dumps(choices, indent=2)}\n\n")

# Check: Should NOT have traveled, and should have refusal content
travel_keywords = ["travel", "arrive", "head to", "go to", "walk to"]
scene_lower = scene.lower()
travel_mentioned = any(kw in scene_lower for kw in travel_keywords)
refusal_keywords = ["can't", "cannot", "impossible", "absurd", "ridiculous", "don't", "won't", "refuse"]
refusal_present = any(kw in scene_lower for kw in refusal_keywords)

record("verify_absurd", "Check refusal behavior", {
    "travel_mentioned": travel_mentioned,
    "refusal_keywords_found": refusal_present,
    "location_unchanged": loc_after == char_get.get("location_id")  # char_get before dm turn
})
prose_lines.append(f"Refusal present? {refusal_present}, Travel mentioned? {travel_mentioned}")

# 4. DM turn — Absurd intent 2: fly to the moon
print("4. DM turn — absurd intent: 'I fly to the moon'")
dm_msg2 = "I fly to the moon."
r = session.post(f"{DM_URL}/dm/turn",
                 json={"character_id": char_id, "message": dm_msg2})
assert r.status_code == 200
dm_data2 = r.json()
scene2 = dm_data2.get("narration", {}).get("scene", "")
loc_after2 = dm_data2.get("character_state", {}).get("location_id")
intent2 = dm_data2.get("server_trace", {}).get("intent_used", {})
record("dm_turn", "Absurd: fly to moon", {
    "intent_type": intent2.get("type"),
    "location_after": loc_after2,
    "scene_preview": scene2[:200]
})
prose_lines.append(f"DM2 intent: {intent2.get('type')}, location: {loc_after2}")
prose_lines.append(f"Scene2: {scene2[:300]}")
with open(dm_prose_path, 'a') as f:
    f.write(f"\n## DM Turn — 'I fly to the moon'\n")
    f.write(f"Timestamp: {now_ts()}\n")
    f.write(f"Intent: {json.dumps(intent2, indent=2)}\n")
    f.write(f"Scene:\n{scene2}\n\n")

# 5. Optional: Probe world graph (ISSUE-017)
print("5. Probing world graph topology...")
r_map = session.get(f"{RULES_URL}/api/map/data")
assert r_map.status_code == 200
map_data = r_map.json()
total = map_data.get("total", 0)
locations = map_data.get("locations", [])
exits_none_count = sum(1 for loc in locations if loc.get("exits") is None)
record("world_probe", "Check exits field in map data", {
    "total": total,
    "exits_None_count": exits_none_count,
    "sample_locations": [loc.get("id") for loc in locations[:5]]
})
prose_lines.append(f"World: total={total}, exits_None={exits_none_count}/{len(locations)}")

# 6. Optional: Explore to check available paths (ISSUE-017 symptom)
print("6. Explore to check available paths...")
r_ex = session.post(f"{RULES_URL}/characters/{char_id}/actions",
                    json={"action_type": "explore"})
assert r_ex.status_code == 200
explore_data = r_ex.json()
avail = explore_data.get("available_paths", [])
record("explore", f"Explore at {initial.get('location_id')}", {
    "available_paths_count": len(avail),
    "paths_sample": avail[:5]
})
prose_lines.append(f"Explore: {len(avail)} available paths")
with open(dm_prose_path, 'a') as f:
    f.write(f"\n## Explore Action\n")
    f.write(f"Available paths: {json.dumps(avail, indent=2)}\n")

# 7. Final character state
print("7. Final character state...")
r_final = session.get(f"{RULES_URL}/characters/{char_id}")
final_data = r_final.json()
record("final", "Final character state", {
    "location_id": final_data.get("location_id"),
    "current_location_id": final_data.get("current_location_id"),
    "hp": final_data.get("hit_points"),
    "flags": final_data.get("narrative_flags", {})
})
prose_lines.append(f"Final: location_id={final_data.get('location_id')}, current_location_id={final_data.get('current_location_id')}")

# Write transcript
transcript_path = os.path.join(run_dir, 'transcript.json')
with open(transcript_path, 'w') as f:
    json.dump(transcript, f, indent=2)

# Write prose
prose_path = os.path.join(run_dir, 'dm-prose.md')
with open(prose_path, 'w') as f:
    f.write("\n".join(prose_lines))

print(f"\nRun complete. Files in {run_dir}/")
print(f"Character ID: {char_id}")
print(f"Smoke earlier: 19/20 PASS (ISSUE-007 failure)")
print(f"Current_location_id after move: {cur_id}")
print(f"World exits None count: {exits_none_count}/{len(locations)}")

# Print summary for final report
print("\n--- SUMMARY ---")
for e in transcript:
    if e['kind'] in ['move', 'dm_turn', 'verify', 'world_probe', 'explore']:
        print(f"{e['timestamp']} {e['kind']}: {e['message']}")
        if e['data']:
            # Print key data points
            for k, v in e['data'].items():
                if k not in ['character_state', 'server_trace']:
                    print(f"  {k}: {v}")
