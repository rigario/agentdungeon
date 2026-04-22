#!/usr/bin/env python3
"""
Full Automated Playthrough Script with Human Gates
==================================================
Creates a fresh test character and runs the complete narrative arc:
Thornhold -> statue -> Aldric -> wolves -> Drenna quest -> Kol -> ending.
Uses BOTH direct API actions and /dm/turn.
Inserts human decision gates at critical junctures.
Saves complete transcript + friction report to JSON.
"""

import httpx
import json
import time
import uuid
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# Configuration (env-overridable)
# ---------------------------------------------------------------------------
RULES_URL = os.environ.get("D20_RULES_URL", "http://localhost:8600")
DM_URL = os.environ.get("DM_URL", "http://localhost:8610")
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class PlaythroughState:
    def __init__(self, char_id: str, name: str):
        self.char_id = char_id
        self.char_name = name
        self.transcript = []
        self.human_gates = []
        self.flags = {}
        self.location_id = None

    def log(self, msg: str, kind: str = "info", data = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "kind": kind,
            "message": msg,
        }
        if data is not None:
            entry["data"] = data if isinstance(data, (dict, list)) else str(data)
        self.transcript.append(entry)
        print(f"[{kind.upper()}] {msg}")

    def gate(self, title: str, description: str, options: List[str], context: Dict = None):
        self.log(f"[GATE] {title} — {description}", "human_gate")
        gate_entry = {
            "gate_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat(),
            "title": title,
            "description": description,
            "options": options,
            "context": context or {},
        }
        self.human_gates.append(gate_entry)
        print(f"\n{'='*60}")
        print(f"GATE: {title}")
        print(f"  {description}")
        print(f"  Options: {', '.join(options)}")
        print(f"{'='*60}\n")
        return gate_entry

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def create_character(client: httpx.Client, name: str, race: str = "Human",
                    class_name: str = "Fighter", background: str = "Soldier") -> str:
    resp = client.post(f"{RULES_URL}/characters", json={
        "name": name, "race": race, "class": class_name, "background": background,
    }, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["id"]

def get_character(client: httpx.Client, char_id: str) -> Dict:
    resp = client.get(f"{RULES_URL}/characters/{char_id}", timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def get_flags(client: httpx.Client, char_id: str) -> Dict[str, str]:
    resp = client.get(f"{RULES_URL}/narrative/flags/{char_id}", timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def do_action(client: httpx.Client, char_id: str, action_type: str,
              target: str = None, detail: str = None) -> Dict:
    payload = {"action_type": action_type}
    if target: payload["target"] = target
    if detail: payload["detail"] = detail
    resp = client.post(f"{RULES_URL}/characters/{char_id}/actions", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def do_dm_turn(client: httpx.Client, char_id: str, message: str, session_id: str = None) -> Dict:
    body = {"character_id": char_id, "message": message}
    if session_id: body["session_id"] = session_id
    resp = client.post(f"{DM_URL}/dm/turn", json=body, timeout=60.0)
    resp.raise_for_status()
    return resp.json()

# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
def phase_create_character(client: httpx.Client, state: PlaythroughState):
    state.log("=== PHASE 1: Create character ===")
    char_id = create_character(client, state.char_name, "Human", "Fighter", "Soldier")
    state.char_id = char_id
    state.log(f"Character created: {char_id}")
    char_data = get_character(client, char_id)
    state.location_id = char_data.get("location_id", "thornhold")
    state.log(f"Starting location: {state.location_id}")
    state.log(f"HP: {char_data.get('hp_current')}/{char_data.get('hp_max')}")

def phase_thornhold_explore(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 2: Thornhold — Statue observation ===")
    state.log("Action: explore in Thornhold")
    result = do_action(client, state.char_id, "explore")
    state.log(f"Explore: {result.get('narration','')[:200]}", "explore")

    flags = get_flags(client, state.char_id)
    if "thornhold_statue_observed" in flags:
        state.log(" thornhold_statue_observed flag SET", "success")
        state.flags["thornhold_statue_observed"] = flags["thornhold_statue_observed"]
    else:
        state.log(" Flag NOT set — unexpected", "warning")

    dm_resp = do_dm_turn(client, state.char_id,
        "I examine the statue in Thornhold's square. What detail do I notice?")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"DM: {scene[:300]}", "dm")

def phase_antechamber_puzzle(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 3: Cave Antechamber — Puzzle ===")
    state.log("Moving to cave-entrance")
    try:
        result = do_action(client, state.char_id, "move", target="cave-entrance")
        state.location_id = "cave-entrance"
    except Exception as e:
        state.log(f"Direct move blocked: {e}", "warning")
        dm_resp = do_dm_turn(client, state.char_id, "I head toward the cave entrance.")
        scene = dm_resp.get("narration", {}).get("scene", "")
        state.log(f"DM: {scene[:200]}")

    state.gate(
        "Antechamber Puzzle",
        "The stone door has three carved fingers (star, crescent, hand). The statue pointed NE. How align?",
        ["Star up, crescent left, hand right (follow statue)",
         "Guess combinations randomly",
         "Search for another clue first"],
    )
    # Auto-continue for automated runs
    if os.environ.get("CONTINUE", "") == "1":
        state.human_gates[-1]["decision"] = "1"
        state.log("Auto-selected option 1")

    dm_resp = do_dm_turn(client, state.char_id,
        "I align the fingers: star up, crescent left, hand right, matching the constellation.")
    state.log(f"Puzzle result: {dm_resp.get('narration',{}).get('scene','')[:300]}", "result")

    flags = get_flags(client, state.char_id)
    if "antechamber_solved" in flags:
        state.flags["antechamber_solved"] = "1"
        state.log(" antechamber_solved flag SET", "success")

def phase_south_road_wolves(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 4: South Road — Wolves ===")
    state.log("Travel to south-rd")
    do_action(client, state.char_id, "move", target="south-rd")
    state.location_id = "south-rd"

    state.log("Exploring to trigger encounter")
    explore = do_action(client, state.char_id, "explore")
    state.log(f"Encounter: {explore.get('narration','')[:300]}", "encounter")

    # Combat via DM
    state.log("Combat: fighting wolves")
    dm_resp = do_dm_turn(client, state.char_id, "I attack the wolves with my longsword.")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"Combat result: {scene[:300]}", "combat")

def phase_sister_drenna_quest(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 5: Sister Drenna — Quest Gate ===")
    state.log("Move to crossroads")
    do_action(client, state.char_id, "move", target="crossroads")
    state.location_id = "crossroads"

    state.log("Talk to Sister Drenna")
    dm_resp = do_dm_turn(client, state.char_id,
        "I approach Sister Drenna. 'Sister, I need to speak with you about the Hollow Eye.'")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"Drenna: {scene[:400]}", "dialogue")

    state.gate(
        "Quest Acceptance — Drenna's Daughter",
        "Drenna reveals she's a doubter and asks you to rescue her daughter from the cult's ritual. Accept?",
        ["Accept — rescue the daughter",
         "Refuse — not getting involved",
         "Report — turn her in to authorities"],
    )
    if os.environ.get("CONTINUE", "") == "1":
        state.human_gates[-1]["decision"] = "1"
        state.log("Auto-accepted quest")

    # Record acceptance
    result = do_action(client, state.char_id, "quest", target="sister_drenna", detail="accept_rescue")
    state.log(f"Quest: {result.get('narration','')[:200]}")

    flags = get_flags(client, state.char_id)
    if "drenna_quest_accepted" in flags:
        state.flags["drenna_quest_accepted"] = "1"
        state.log(" drenna_quest_accepted flag SET", "success")

def phase_kol_encounter(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 6: Brother Kol — Cave Depths ===")
    state.log("Proceed to cave-depths")
    try:
        do_action(client, state.char_id, "move", target="cave-depths")
        state.location_id = "cave-depths"
    except Exception as e:
        dm_resp = do_dm_turn(client, state.char_id, "I venture deeper into the cave system.")

    state.log("Searching for Kol")
    explore = do_action(client, state.char_id, "explore")
    state.log(f"Found: {explore.get('narration','')[:200]}")

    state.log("Confronting Kol")
    dm_resp = do_dm_turn(client, state.char_id,
        "I face Brother Kol at the ritual site. 'The sacrifices end now.'")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"Kol confrontation: {scene[:400]}", "dialogue")

    state.gate(
        "Brother Kol — Final Choice",
        "Kol is the sacrifice. He knows the truth about the Hunger. What do you do?",
        ["Fight — kill Kol to stop the ritual",
         "Persuade — convince him to surrender",
         "Commune — merge with understanding (requires kol_backstory_known)"],
    )
    if os.environ.get("CONTINUE", "") == "1":
        state.human_gates[-1]["decision"] = "1"
        state.log("Auto-selected Fight")

    choice_map = {
        "1": "I attack Brother Kol to stop the sacrifice.",
        "2": "I try to persuade Kol to stand down.",
        "3": "I reach out in communion with the Hunger's truth.",
    }
    decision = state.human_gates[-1].get("decision", "1")
    message = choice_map.get(decision, "I act according to my judgment.")
    dm_resp = do_dm_turn(client, state.char_id, message)
    state.log(f"Outcome: {dm_resp.get('narration',{}).get('scene','')[:300]}", "outcome")

def phase_final_summary(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 7: Final Summary ===")
    char_data = get_character(client, state.char_id)
    flags = get_flags(client, state.char_id)

    state.log(f"Level: {char_data.get('level')} | HP: {char_data.get('hp_current')}/{char_data.get('hp_max')}")
    state.log(f"Location: {char_data.get('location_id')}")
    state.log(f"Mark: {char_data.get('mark_of_dreamer_stage',0)}")
    state.log(f"Flags set: {list(flags.keys())}")

    # Ending check via introspect
    resp = client.get(f"{RULES_URL}/narrative-introspect/character/{state.char_id}/summary", timeout=TIMEOUT)
    if resp.status_code == 200:
        summary = resp.json()
        for e in summary.get("endings", []):
            print(f"Ending: {e['ending_name']} — reachable={e['is_reachable']}, missing={e.get('missing_requirements',[])}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  D20 Full Playthrough with Human Gates")
    print("=" * 60)
    print(f"Rules: {RULES_URL}")
    print(f"DM:     {DM_URL}")
    print()

    char_name = f"GateTest-{uuid.uuid4().hex[:6]}"
    state = PlaythroughState(None, char_name)

    with httpx.Client(timeout=TIMEOUT) as client:
        # Health
        try:
            client.get(f"{RULES_URL}/health", timeout=10)
            client.get(f"{DM_URL}/dm/health", timeout=10)
        except Exception as e:
            print(f"Health check failed: {e}")
            return

        # Execute
        phase_create_character(client, state)
        phase_thornhold_explore(client, state)
        phase_antechamber_puzzle(client, state)
        phase_south_road_wolves(client, state)
        phase_sister_drenna_quest(client, state)
        phase_kol_encounter(client, state)
        phase_final_summary(client, state)

        # Save report
        report = {
            "playthrough_id": str(uuid.uuid4()),
            "character_name": state.char_name,
            "character_id": state.char_id,
            "timestamp": datetime.utcnow().isoformat(),
            "transcript": state.transcript,
            "human_gates": state.human_gates,
            "final_flags": state.flags,
        }
        outfile = f"playthrough_{state.char_id}.json"
        with open(outfile, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved: {outfile}")
        print(f"Human gates: {len(state.human_gates)}")
        print("=== COMPLETE ===")

if __name__ == "__main__":
    main()

