#!/usr/bin/env python3
"""
D20 Playtest Heartbeat — Scenario D (NPC Quest Chain)
Run: CONTINUE=1 python scripts/heartbeat_scenario_d.py
"""
import os
import json
import uuid
import datetime
import requests

RULES_URL = os.environ.get("D20_RULES_URL", "https://agentdungeon.com")
DM_URL = os.environ.get("DM_URL", "https://agentdungeon.com")

def main():
    char_name = f"hb-d-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    char_id = None
    transcript = []
    final_flags = {}

    def log(kind, endpoint, status=200, data=None, excerpt=""):
        transcript.append({
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "kind": kind,
            "endpoint": endpoint,
            "status": status,
            "excerpt": excerpt[:200],
            "data": data,
        })

    # --- Phase 1: Character creation ---
    resp = requests.post(f"{RULES_URL}/characters", json={
        "name": char_name,
        "race": "Human",
        "class": "Fighter",
        "background": "Soldier"
    })
    resp.raise_for_status()
    char_data = resp.json()
    char_id = char_data["id"]
    log("create", "/characters", resp.status_code,
        data={"location_id": char_data.get("location_id"), "hp": char_data.get("hp")},
        excerpt=f"created id={char_id} location={char_data.get('location_id')}")

    # --- Phase 2: Initial explore (statue gate) ---
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "explore"})
    log("explore", f"/characters/{char_id}/actions", resp.status_code,
        excerpt=f"explore Thornhold")
    resp.raise_for_status()

    # Verify flag
    resp = requests.get(f"{RULES_URL}/narrative/flags/{char_id}")
    flag_data = resp.json()
    final_flags["thornhold_statue_observed"] = flag_data.get("thornhold_statue_observed", "0")
    log("flags", f"/narrative/flags/{char_id}", resp.status_code,
        excerpt=f"statue_observed={final_flags['thornhold_statue_observed']}")

    # --- Phase 3: Move to south-road ---
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "south-road"})
    move_data = resp.json()
    log("move", f"/characters/{char_id}/actions (south-road)", resp.status_code,
        data={"success": move_data.get("success"), "location": move_data.get("character_state",{}).get("location_id")},
        excerpt=f"success={move_data.get('success')}, location={move_data.get('character_state',{}).get('location_id')}")

    # GET current state to verify location persistence (ISSUE-007/016 check)
    resp = requests.get(f"{RULES_URL}/characters/{char_id}")
    char_resp = resp.json()
    location_id = char_resp.get("location_id")
    current_location_id = char_resp.get("current_location_id")
    log("get", f"/characters/{char_id}", resp.status_code,
        data={"location_id": location_id, "current_location_id": current_location_id},
        excerpt=f"location_id={location_id}, current_location_id={current_location_id}")

    # --- Phase 4: DM turn — interact with Sister Drenna ---
    resp = requests.post(f"{DM_URL}/dm/turn", json={
        "character_id": char_id,
        "message": "I want to speak with Sister Drenna."
    })
    dm_data = resp.json()
    narration = dm_data.get("narration", {})
    scene = narration.get("scene", "")
    choices = dm_data.get("choices", [])
    log("dm_turn", "/dm/turn (Drenna)", resp.status_code,
        data={"scene_preview": scene[:80], "choices": choices},
        excerpt=f"scene: {scene[:100]}")

    # --- Phase 5: Quest attempt (accept Drenna quest) ---
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "quest", "target": "drenna_rescue", "details": {"action": "accept"}})
    quest_data = resp.json()
    log("quest", f"/characters/{char_id}/actions (quest accept)", resp.status_code,
        data={"success": quest_data.get("success")},
        excerpt=f"quest accept response: {str(quest_data)[:150]}")

    # Re-check flags
    resp = requests.get(f"{RULES_URL}/narrative/flags/{char_id}")
    flag_data = resp.json()
    final_flags["drenna_quest_accepted"] = flag_data.get("drenna_quest_accepted", "0")
    log("flags_post_quest", f"/narrative/flags/{char_id}", resp.status_code,
        excerpt=f"drenna_quest={final_flags['drenna_quest_accepted']}")

    # --- Phase 6: Navigate to cave-depths (via thornhold workaround) ---
    # Backtrack to thornhold first
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "thornhold"})
    log("move_back", f"move to thornhold", resp.status_code,
        excerpt=f"backtrack={resp.json().get('success')}")

    # Move thornhold → forest-edge
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "forest-edge"})
    move_fe = resp.json()
    log("move_forest_edge", f"move forest-edge", resp.status_code,
        data={"success": move_fe.get("success"), "location": move_fe.get("character_state",{}).get("location_id")},
        excerpt=f"success={move_fe.get('success')}")

    # Explore forest-edge (may trigger combat or loot)
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "explore"})
    explore_fe = resp.json()
    log("explore_forest_edge", f"explore forest-edge", resp.status_code,
        data={"combat": explore_fe.get("combat"), "events": [e.get("type") for e in explore_fe.get("events",[])]},
        excerpt=f"explore: combat={explore_fe.get('combat')}")

    # Move deep-forest
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "deep-forest"})
    log("move_deep_forest", f"move deep-forest", resp.status_code,
        excerpt=f"success={resp.json().get('success')}")

    # Explore deep-forest
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "explore"})
    log("explore_deep_forest", f"explore deep-forest", resp.status_code)

    # Move cave-entrance
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "cave-entrance"})
    log("move_cave_entrance", f"move cave-entrance", resp.status_code)

    # Explore cave-entrance (unlock cave-depths)
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "explore"})
    log("explore_cave_entrance", f"explore cave-entrance", resp.status_code)

    # Move to cave-depths
    resp = requests.post(f"{RULES_URL}/characters/{char_id}/actions",
        json={"action_type": "move", "target": "cave-depths"})
    log("move_cave_depths", f"move cave-depths", resp.status_code,
        excerpt=f"success={resp.json().get('success')}")

    # --- Phase 7: DM turn — interact with Brother Kol ---
    resp = requests.post(f"{DM_URL}/dm/turn", json={
        "character_id": char_id,
        "message": "Brother Kol, I want to understand your story."
    })
    dm_kol = resp.json()
    narration_kol = dm_kol.get("narration", {})
    scene_kol = narration_kol.get("scene", "")
    choices_kol = dm_kol.get("choices", [])
    log("dm_kol", "/dm/turn (Kol)", resp.status_code,
        data={"scene_preview": scene_kol[:80], "choices": choices_kol},
        excerpt=f"Kol scene: {scene_kol[:120]}")

    # Post-Kol: check kol_backstory_known flag
    resp = requests.get(f"{RULES_URL}/narrative/flags/{char_id}")
    final_flag_data = resp.json()
    final_flags["kol_backstory_known"] = final_flag_data.get("kol_backstory_known", "0")
    final_flags["kol_brother_met"] = final_flag_data.get("kol_brother_met", "0")
    log("final_flags", f"/narrative/flags/{char_id}", resp.status_code,
        excerpt=f"kol_backstory_known={final_flags['kol_backstory_known']}, kol_brother_met={final_flags['kol_brother_met']}")

    # Summary
    summary = {
        "playthrough_id": str(uuid.uuid4()),
        "character_name": char_name,
        "character_id": char_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "rules_url": RULES_URL,
        "dm_url": DM_URL,
        "transcript": transcript,
        "final_flags": final_flags,
        "scenario": "D",
    }
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
