#!/usr/bin/env python3
"""
Supplemental probe: ISSUE-016 — in-location statue examination routing.
Continuation of Scenario B run: after moving to thornhold, explore to set flag, then examine statue.
"""

import os, json, datetime, requests

RULES_URL = "https://agentdungeon.com"
DM_URL = "https://agentdungeon.com"
CHAR_ID = "hbb-202604251545-2bfa3d"  # from previous run
RUN_DIR = "playtest-runs/heartbeat-b-20260425T154516"

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

def now_ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

prose_path = os.path.join(RUN_DIR, 'dm-prose.md')
transcript_path = os.path.join(RUN_DIR, 'transcript.json')

# Load existing transcript
with open(transcript_path, 'r') as f:
    transcript = json.load(f)

def record(kind, message, data=None):
    entry = {"timestamp": now_ts(), "kind": kind, "message": message, "data": data or {}}
    transcript.append(entry)
    with open(prose_path, 'a') as pf:
        pf.write(f"\n[{now_ts()}] {kind.upper()}: {message}\n")
        if data:
            pf.write(f"  Data: {json.dumps(data, ensure_ascii=False)[:500]}\n")

# 1. Explore thornhold (should set statue flag)
print("Exploring thornhold to discover statue...")
r = session.post(f"{RULES_URL}/characters/{CHAR_ID}/actions",
                 json={"action_type": "explore"})
assert r.status_code == 200
explore_data = r.json()
avail = explore_data.get("available_paths", [])
narration = explore_data.get("narration", "")
record("explore_thornhold", "Explore at thornhold", {
    "available_paths": avail,
    "narration_preview": narration[:200]
})
print(f"   Explore returned {len(avail)} paths")

# Check flag
r = session.get(f"{RULES_URL}/narrative/flags/{CHAR_ID}")
flags_data = r.json()
statue_flag = flags_data.get("flags", {}).get("thornhold_statue_observed")
record("flags_after_explore", "Check flags", {"thornhold_statue_observed": statue_flag})
print(f"   thornhold_statue_observed = {statue_flag}")

# 2. DM turn — examine statue (core ISSUE-016 test)
print("DM turn: 'I examine the statue carefully'")
r = session.post(f"{DM_URL}/dm/turn",
                 json={"character_id": CHAR_ID, "message": "I examine the statue carefully."})
assert r.status_code == 200
dm_data = r.json()
intent = dm_data.get("server_trace", {}).get("intent_used", {})
narration = dm_data.get("narration", {})
scene = narration.get("scene", "")
choices = dm_data.get("choices", [])
loc_after = dm_data.get("character_state", {}).get("location_id")

record("dm_turn_examine", "Examine statue interaction", {
    "intent_type": intent.get("type"),
    "intent_target": intent.get("target"),
    "location_after": loc_after,
    "choices": [c.get("label") for c in choices],
    "scene_preview": scene[:300]
})
print(f"   Intent: {intent}")
print(f"   Scene: {scene[:200]}")

# Append full prose
with open(prose_path, 'a') as pf:
    pf.write(f"\n## DM Turn — Examine Statue\n")
    pf.write(f"Timestamp: {now_ts()}\n")
    pf.write(f"Intent: {json.dumps(intent, indent=2)}\n")
    pf.write(f"Scene:\n{scene}\n\n")
    pf.write(f"Choices:\n{json.dumps(choices, indent=2)}\n\n")

# Verification: Check for misrouting (teleport)
r_final = session.get(f"{RULES_URL}/characters/{CHAR_ID}")
final_data = r_final.json()
loc_final = final_data.get("location_id")
cur_final = final_data.get("current_location_id")
record("final_verify", "Post-interact state", {
    "location_id": loc_final,
    "current_location_id": cur_final,
    "flags": final_data.get("narrative_flags", {})
})
print(f"   Final location: {loc_final}, current_location_id: {cur_final}")

# Save updated transcript
with open(transcript_path, 'w') as f:
    json.dump(transcript, f, indent=2)

print("\nSupplemental probe complete.")
print(f"ISSUE-016 test: intent_type={intent.get('type')}, target={intent.get('target')}")
# Determine ISSUE-016 status:
if intent.get('type') == 'general' and loc_final != 'thornhold':
    print("ISSUE-016 likely REPRODUCED: general intent caused travel away from location")
elif 'statue' in (intent.get('target') or '').lower():
    print("ISSUE-016 possibly FIXED: intent classified as interact and target includes statue")
else:
    print("ISSUE-016: inconclusive — review DM prose")
