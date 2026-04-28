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
from pathlib import Path
from typing import Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# Configuration (env-overridable)
# ---------------------------------------------------------------------------
RULES_URL = os.environ.get("D20_RULES_URL", "http://localhost:8600")
DM_URL = os.environ.get("DM_URL", "http://localhost:8610")
TIMEOUT = 30.0
PLAYTEST_RUNS_DIR = Path(os.environ.get("PLAYTEST_RUNS_DIR", "playtest-runs"))

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
        self.dm_turns = []
        self.dm_turn_counter = 0
        self.run_started = datetime.utcnow()
        self.artifact_dir = None

    def prepare_artifacts(self):
        if self.artifact_dir is not None:
            return
        safe_char = self.char_id or "pending-character"
        stamp = self.run_started.strftime("%Y%m%dT%H%M%SZ")
        self.artifact_dir = PLAYTEST_RUNS_DIR / f"{stamp}-{safe_char}"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

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

    def dm_turn(self, client: httpx.Client, message: str, label: str = None, session_id: str = None) -> Dict:
        """Call /dm/turn and retain the full DM response for prose review."""
        self.prepare_artifacts()
        self.dm_turn_counter += 1
        turn_number = self.dm_turn_counter
        requested_at = datetime.utcnow().isoformat()
        location_before = self.location_id
        response = do_dm_turn(client, self.char_id, message, session_id=session_id)
        logged_at = datetime.utcnow().isoformat()
        narration = response.get("narration") or {}
        scene = narration.get("scene", "") if isinstance(narration, dict) else str(narration)
        npc_lines = narration.get("npc_lines", []) if isinstance(narration, dict) else []
        choices = response.get("choices") or []
        mechanics = response.get("mechanics") or {}
        server_trace = response.get("server_trace") or {}
        entry = {
            "turn_number": turn_number,
            "anchor": f"turn-{turn_number:03d}",
            "label": label,
            "requested_at": requested_at,
            "logged_at": logged_at,
            "character_id": self.char_id,
            "location_before": location_before,
            "message": message,
            "status": 200,
            "session_id": response.get("session_id"),
            "server_endpoint_called": server_trace.get("server_endpoint_called"),
            "narration_scene": scene,
            "npc_lines": npc_lines,
            "choices": choices,
            "mechanics": mechanics,
            "server_trace": server_trace,
            "raw_response": response,
        }
        self.dm_turns.append(entry)
        self.transcript.append({
            "timestamp": logged_at,
            "kind": "dm_turn",
            "message": message,
            "data": {
                "turn_number": turn_number,
                "label": label,
                "session_id": response.get("session_id"),
                "server_endpoint_called": server_trace.get("server_endpoint_called"),
                "full_response_logged": True,
                "prose_log_anchor": f"turn-{turn_number:03d}",
            },
        })
        print(f"[DM_TURN] turn-{turn_number:03d} {label or ''} session={response.get('session_id')}")
        return response

    def write_artifacts(self, report: Dict):
        self.prepare_artifacts()
        transcript_path = self.artifact_dir / "transcript.json"
        prose_path = self.artifact_dir / "dm-prose.md"
        report["artifact_paths"] = {
            "transcript_json": str(transcript_path),
            "dm_prose_markdown": str(prose_path),
        }
        with transcript_path.open("w") as f:
            json.dump(report, f, indent=2)
        with prose_path.open("w") as f:
            f.write(render_dm_prose_markdown(self))
        return transcript_path, prose_path

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

def render_dm_prose_markdown(state: PlaythroughState) -> str:
    lines = []
    lines.append(f"# D20 DM Prose Log — {state.char_name}")
    lines.append("")
    lines.append(f"- Character ID: `{state.char_id}`")
    lines.append(f"- Started: {state.run_started.isoformat()}Z")
    lines.append(f"- Rules URL: {RULES_URL}")
    lines.append(f"- DM URL: {DM_URL}")
    lines.append("")
    lines.append("This file intentionally preserves the full DM prose with no truncation for narrative review.")
    lines.append("")
    for turn in state.dm_turns:
        lines.append(f"## Turn {turn['turn_number']:03d} — {turn['logged_at']}")
        lines.append("")
        if turn.get("label"):
            lines.append(f"**Label:** {turn['label']}")
        lines.append(f"**Tester message:** {turn['message']}")
        lines.append(f"**Status:** {turn['status']}")
        lines.append(f"**Session:** {turn.get('session_id')}")
        lines.append(f"**Location before:** {turn.get('location_before')}")
        lines.append(f"**Endpoint called:** {turn.get('server_endpoint_called')}")
        lines.append("")
        lines.append("### DM scene")
        lines.append("")
        scene = turn.get("narration_scene") or ""
        lines.append(scene)
        lines.append("")
        lines.append("### NPC lines")
        lines.append("")
        npc_lines = turn.get("npc_lines") or []
        if npc_lines:
            for npc in npc_lines:
                if isinstance(npc, dict):
                    speaker = npc.get("speaker") or "Unknown"
                    text = npc.get("text") or ""
                    lines.append(f"- **{speaker}:** {text}")
                else:
                    lines.append(f"- {npc}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("### Choices")
        lines.append("")
        choices = turn.get("choices") or []
        if choices:
            for idx, choice in enumerate(choices, start=1):
                if isinstance(choice, dict):
                    label = choice.get("label") or choice.get("id") or str(choice)
                    lines.append(f"{idx}. {label}")
                else:
                    lines.append(f"{idx}. {choice}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("### Mechanics summary")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(turn.get("mechanics") or {}, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
        lines.append("### Server trace")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(turn.get("server_trace") or {}, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"

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


def safe_action(client: httpx.Client, char_id: str, action_type: str,
                target: str = None, detail: str = None) -> Dict | None:
    """Call do_action but return None on HTTP error instead of crashing.
    Use when the action is optional or has a DM-turn fallback."""
    try:
        return do_action(client, char_id, action_type, target=target, detail=detail)
    except httpx.HTTPStatusError as e:
        resp = e.response
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        state_msg = ""
        detail = body.get("detail") or body.get("error") or f"HTTP {resp.status_code}"
        # detail can be a dict, string, or list — normalize to string
        if isinstance(detail, str):
            state_msg = detail
        elif isinstance(detail, dict):
            state_msg = str(detail)
        else:
            state_msg = str(detail) if detail else f"HTTP {resp.status_code}"
        if resp.status_code == 403:
            # combat_active or character_deceased — get reason
            if "combat" in state_msg.lower() or "combat_active" in state_msg:
                return {"success": False, "error": "combat_active", "status_code": 403, "body": body}
            if "deceased" in state_msg.lower() or "character_deceased" in state_msg:
                return {"success": False, "error": "character_deceased", "status_code": 403, "body": body}
        return {"success": False, "error": state_msg, "status_code": resp.status_code, "body": body}
    except Exception as e:
        return {"success": False, "error": repr(e), "status_code": None, "body": {}}

def do_dm_turn(client: httpx.Client, char_id: str, message: str, session_id: str = None) -> Dict:
    body = {"character_id": char_id, "message": message}
    if session_id: body["session_id"] = session_id
    try:
        resp = client.post(f"{DM_URL}/dm/turn", json=body, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        resp = e.response
        try:
            body = resp.json()
        except Exception:
            body = {"error": f"HTTP {resp.status_code}"}
        # Return a graceful error response instead of crashing
        return {
            "narration": {"scene": f"[DM error {resp.status_code}: {body.get('detail', body.get('error', 'unavailable'))}]"},
            "choices": [],
            "mechanics": {},
            "server_trace": {},
            "_dm_error": body.get("detail", body.get("error", f"HTTP {resp.status_code}")),
            "_http_status": resp.status_code,
        }
    except Exception as e:
        return {
            "narration": {"scene": f"[DM unavailable: {repr(e)}]"},
            "choices": [],
            "mechanics": {},
            "server_trace": {},
            "_dm_error": repr(e),
            "_http_status": None,
        }

# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
def phase_create_character(client: httpx.Client, state: PlaythroughState):
    state.log("=== PHASE 1: Create character ===")
    char_id = create_character(client, state.char_name, "Human", "Fighter", "Soldier")
    state.char_id = char_id
    state.log(f"Character created: {char_id}")
    char_data = get_character(client, char_id)
    state.location_id = char_data.get("location_id", "rusty-tankard")
    state.log(f"Spawning location: {state.location_id}")
    state.log(f"HP: {char_data.get('hp_current')}/{char_data.get('hp_max')}")

    # Ensure character is at Thornhold before statue phase
    if state.location_id != "thornhold":
        state.log(f"Moving from {state.location_id} to Thornhold")
        result = safe_action(client, state.char_id, "move", target="thornhold")
        if result and result.get("success"):
            state.location_id = result.get("character_state", {}).get("location_id") or "thornhold"
            state.log(f"Moved to: {state.location_id}")
        else:
            dm_resp = state.dm_turn(client, "I go to the Thornhold town square.", label="navigate to thornhold")
            char_data = get_character(client, state.char_id)
            state.location_id = char_data.get("location_id")
            state.log(f"DM routed to: {state.location_id}")

def phase_thornhold_explore(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 2: Thornhold — Statue observation ===")
    state.log("Action: explore in Thornhold")
    result = safe_action(client, state.char_id, "explore")
    if result:
        state.log(f"Explore: {result.get('narration','')[:200]}", "explore")
    else:
        state.log("Explore blocked (HTTP error) — continuing via DM", "warning")

    flags = get_flags(client, state.char_id)
    if "thornhold_statue_observed" in flags:
        state.log(" thornhold_statue_observed flag SET", "success")
        state.flags["thornhold_statue_observed"] = flags["thornhold_statue_observed"]
    else:
        state.log(" Flag NOT set — unexpected", "warning")

    dm_resp = state.dm_turn(client,
        "I examine the statue in Thornhold's square. What detail do I notice?",
        label="statue examination")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"DM: {scene[:300]}", "dm")

def phase_antechamber_puzzle(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 3: Cave Antechamber — Puzzle ===")
    # Correct world path: cave-entrance is reachable from deep-forest, NOT directly from Thornhold.
    # If not already at cave-entrance, route via forest-edge -> deep-forest.
    if state.location_id not in ("cave-entrance", "cave-depths", "deep-forest"):
        state.log("Routing to cave-entrance via forest-edge -> deep-forest")
        result = safe_action(client, state.char_id, "move", target="forest-edge")
        if result and result.get("success"):
            state.location_id = result.get("character_state", {}).get("location_id") or "forest-edge"
            state.log(f"Moved to: {state.location_id}")
        else:
            dm_resp = state.dm_turn(client, "I travel to the forest edge of Whisperwood.", label="navigate forest-edge")
            char_data = get_character(client, state.char_id)
            state.location_id = char_data.get("location_id")

        state.log("Proceeding to deep forest")
        result = safe_action(client, state.char_id, "move", target="deep-forest")
        if result and result.get("success"):
            state.location_id = result.get("character_state", {}).get("location_id") or "deep-forest"
            state.log(f"Moved to: {state.location_id}")
        else:
            dm_resp = state.dm_turn(client, "I venture deeper into Whisperwood toward the cave entrance.", label="navigate deep-forest")
            char_data = get_character(client, state.char_id)
            state.location_id = char_data.get("location_id")

    state.log("Moving to cave-entrance")
    result = safe_action(client, state.char_id, "move", target="cave-entrance")
    if result is None or not result.get("success"):
        err = (result or {}).get("error", "move failed") if result else "HTTP error"
        state.log(f"Move to cave-entrance blocked ({err}) — trying DM turn", "warning")
        dm_resp = state.dm_turn(client, "I head toward the cave entrance.", label="navigate to cave entrance")
        if dm_resp.get("_dm_error"):
            state.log(f"DM unavailable ({dm_resp.get('_dm_error')}) — skipping antechamber puzzle", "warning")
            return
        scene = dm_resp.get("narration", {}).get("scene", "")
        state.log(f"DM: {scene[:200]}")
        char_data = get_character(client, state.char_id)
        state.location_id = char_data.get("location_id")
    else:
        state.location_id = result.get("character_state", {}).get("location_id") or "cave-entrance"
        state.log(f"Moved to: {state.location_id}")

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

    dm_resp = state.dm_turn(client,
        "I align the fingers: star up, crescent left, hand right, matching the constellation.",
        label="antechamber puzzle solution")
    state.log(f"Puzzle result: {dm_resp.get('narration',{}).get('scene','')[:300]}", "result")

    flags = get_flags(client, state.char_id)
    if "antechamber_solved" in flags:
        state.flags["antechamber_solved"] = "1"
        state.log(" antechamber_solved flag SET", "success")

def phase_south_road_wolves(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 4: South Road — Wolves ===")
    state.log("Travel to south-road")
    result = safe_action(client, state.char_id, "move", target="south-road")
    if result is None or not result.get("success"):
        err = (result or {}).get("error", "move failed") if result else "HTTP error"
        state.log(f"Move to south-road blocked ({err}) — trying DM turn", "warning")
        dm_resp = state.dm_turn(client, "I travel the south road toward the forest.", label="travel south road")
        if dm_resp.get("_dm_error"):
            state.log(f"DM unavailable ({dm_resp.get('_dm_error')}) — cannot travel", "warning")
            char_data = get_character(client, state.char_id)
            state.location_id = char_data.get("location_id")
            # Detect death and stop progression
            if char_data.get("conditions") or "deceased" in str(state.location_id).lower():
                state.log("Character deceased — halting progression", "warning")
                return
        else:
            scene = dm_resp.get("narration", {}).get("scene", "")
            state.log(f"DM narration: {scene[:200]}")
            char_data = get_character(client, state.char_id)
            state.location_id = char_data.get("location_id")
            # Check if character stuck in combat
            if char_data.get("combat_state") == "combat_active":
                state.log("Character in combat_active — resolving via DM combat turn", "warning")
                dm_resp = state.dm_turn(client, "I stand ready and await the wolves' approach.", label="combat resolve")
    else:
        state.location_id = result.get("character_state", {}).get("location_id") or "south-road"
        state.log(f"Moved to: {state.location_id}")

    state.log("Exploring to trigger encounter")
    explore = safe_action(client, state.char_id, "explore")
    if explore:
        state.log(f"Encounter: {explore.get('narration','')[:300]}", "encounter")
    else:
        state.log("Explore blocked (HTTP error) — continuing", "warning")

    # Combat via DM
    state.log("Combat: fighting wolves")
    dm_resp = state.dm_turn(client, "I attack the wolves with my longsword.", label="wolf combat")
    scene = dm_resp.get("narration", {}).get("scene", "")
    state.log(f"Combat result: {scene[:300]}", "combat")

def phase_sister_drenna_quest(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 5: Sister Drenna — Quest Gate ===")
    state.log("Move to crossroads")
    result = safe_action(client, state.char_id, "move", target="crossroads")
    if result is None or not result.get("success"):
        err = (result or {}).get("error", "move failed") if result else "HTTP error"
        state.log(f"Move to crossroads blocked ({err}) — trying DM turn", "warning")
        dm_resp = state.dm_turn(client, "I make my way to the crossroads.", label="travel crossroads")
        char_data = get_character(client, state.char_id)
        state.location_id = char_data.get("location_id")
    else:
        state.location_id = result.get("character_state", {}).get("location_id") or "crossroads"
        state.log(f"Moved to: {state.location_id}")

    state.log("Talk to Sister Drenna")
    dm_resp = state.dm_turn(client,
        "I approach Sister Drenna. 'Sister, I need to speak with you about the Hollow Eye.'",
        label="sister drenna dialogue")
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
    result = safe_action(client, state.char_id, "quest", target="sister_drenna", detail="accept_rescue")
    if result:
        state.log(f"Quest: {result.get('narration','')[:200]}")
    else:
        state.log("Quest acceptance failed (HTTP error) — attempting DM fallback", "warning")

    flags = get_flags(client, state.char_id)
    if "drenna_quest_accepted" in flags:
        state.flags["drenna_quest_accepted"] = "1"
        state.log(" drenna_quest_accepted flag SET", "success")

def phase_kol_encounter(client: httpx.Client, state: PlaythroughState):
    state.log("\n=== PHASE 6: Brother Kol — Cave Depths ===")
    state.log("Proceed to cave-depths")
    result = safe_action(client, state.char_id, "move", target="cave-depths")
    if result is None or not result.get("success"):
        err = (result or {}).get("error", "move failed") if result else "HTTP error"
        state.log(f"Move to cave-depths blocked ({err}) — trying DM turn", "warning")
        dm_resp = state.dm_turn(client, "I venture deeper into the cave system.", label="travel cave depths")
        char_data = get_character(client, state.char_id)
        state.location_id = char_data.get("location_id")
    else:
        state.location_id = result.get("character_state", {}).get("location_id") or "cave-depths"
        state.log(f"Moved to: {state.location_id}")

    state.log("Searching for Kol")
    explore = safe_action(client, state.char_id, "explore")
    if explore:
        state.log(f"Found: {explore.get('narration','')[:200]}")
    else:
        state.log("Explore blocked (HTTP error) — continuing", "warning")

    state.log("Confronting Kol")
    dm_resp = state.dm_turn(client,
        "I face Brother Kol at the ritual site. 'The sacrifices end now.'",
        label="brother kol confrontation")
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
    dm_resp = state.dm_turn(client, message, label="final choice outcome")
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

        run_error = None
        try:
            # Execute
            phase_create_character(client, state)
            phase_thornhold_explore(client, state)
            phase_antechamber_puzzle(client, state)
            phase_south_road_wolves(client, state)
            phase_sister_drenna_quest(client, state)
            phase_kol_encounter(client, state)
            phase_final_summary(client, state)
        except Exception as exc:
            run_error = repr(exc)
            state.log(f"Playthrough aborted: {run_error}", "error")
        finally:
            # Always save structured transcript + full DM prose log, even on failure.
            report = {
                "playthrough_id": str(uuid.uuid4()),
                "character_name": state.char_name,
                "character_id": state.char_id,
                "timestamp": datetime.utcnow().isoformat(),
                "rules_url": RULES_URL,
                "dm_url": DM_URL,
                "run_error": run_error,
                "transcript": state.transcript,
                "dm_turns": state.dm_turns,
                "human_gates": state.human_gates,
                "final_flags": state.flags,
            }
            transcript_path, prose_path = state.write_artifacts(report)
            print(f"\nTranscript saved: {transcript_path}")
            print(f"DM prose saved:   {prose_path}")
            print(f"Human gates: {len(state.human_gates)}")
            print(f"DM turns logged: {len(state.dm_turns)}")
            if run_error:
                print(f"RUN ERROR: {run_error}")
                raise SystemExit(1)
            print("=== COMPLETE ===")

if __name__ == "__main__":
    main()

