#!/usr/bin/env python3
"""Scenario A — Character Creation + First Steps via DM agent path."""
import httpx, json, uuid, os
from datetime import datetime, timezone
from pathlib import Path

RULES = "https://d20.holocronlabs.ai"
DM = "https://d20.holocronlabs.ai"
TIMEOUT = 90.0

def run():
    char_name = f"PlayA-{uuid.uuid4().hex[:6]}"
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = Path("playtest-runs") / f"{run_ts}-{char_name}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    transcript = []
    dm_turns = []

    with httpx.Client(timeout=TIMEOUT) as client:
        # Phase 1: Health
        print("=== Phase 1: Health checks ===")
        h1 = client.get(f"{RULES}/health")
        h2 = client.get(f"{DM}/dm/health")
        print(f"  rules={h1.status_code} dm={h2.status_code}")
        transcript.append({"step": "health", "rules": h1.status_code, "dm": h2.status_code})

        # Phase 2: Create character
        print("\n=== Phase 2: Create character ===")
        resp = client.post(f"{RULES}/characters", json={
            "name": char_name, "race": "Human", "class": "Fighter", "background": "Soldier"
        })
        char = resp.json()
        cid = char["id"]
        loc = char.get("location_id")
        print(f"  Created: {cid} at {loc}")
        transcript.append({"step": "create", "status": resp.status_code, "id": cid, "location": loc})

        # Phase 3: Explore Thornhold
        print("\n=== Phase 3: Explore ===")
        resp = client.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
        data = resp.json()
        narr = data.get("narration", "")
        print(f"  Explore: status={resp.status_code} success={data.get('success')}")
        print(f"  Narration: {narr[:300]}")
        transcript.append({"step": "explore", "status": resp.status_code, "success": data.get("success"), "narration": narr[:200]})

        # Flag check
        flags = client.get(f"{RULES}/narrative/flags/{cid}").json()
        print(f"  Flags: {flags}")
        transcript.append({"step": "check_flags", "flags": flags})

        # Phase 4: DM turn — look around
        print("\n=== Phase 4: DM turns ===")
        session_id = None
        turn_num = 0

        # DM Turn 1: Look around
        turn_num += 1
        body = {"character_id": cid, "message": "I look around Thornhold. What do I notice?"}
        resp = client.post(f"{DM}/dm/turn", json=body, timeout=120)
        data = resp.json()
        session_id = data.get("session_id", session_id)
        scene = (data.get("narration") or {}).get("scene", "")
        npc_lines = (data.get("narration") or {}).get("npc_lines", [])
        choices = data.get("choices") or []
        trace = data.get("server_trace") or {}
        dm_turns.append({
            "turn": turn_num, "label": "look around thornhold",
            "status": resp.status_code, "session_id": session_id,
            "endpoint": trace.get("server_endpoint_called"),
            "scene": scene, "npc_lines": npc_lines, "choices": choices,
            "raw": data,
        })
        print(f"  Turn {turn_num} status={resp.status_code} session={session_id}")
        print(f"  Scene: {scene[:300]}")
        print(f"  NPC lines: {npc_lines}")
        if choices:
            for i, c in enumerate(choices, 1):
                lbl = c.get("label", c) if isinstance(c, dict) else c
                print(f"  Choice {i}: {lbl}")
        transcript.append({"step": f"dm_turn_{turn_num}", "status": resp.status_code, "session_id": session_id})

        # DM Turn 2: Examine statue
        turn_num += 1
        body = {"character_id": cid, "message": "I examine the old stone statue in the town square. What details do I notice?", "session_id": session_id}
        resp = client.post(f"{DM}/dm/turn", json=body, timeout=120)
        data = resp.json()
        scene2 = (data.get("narration") or {}).get("scene", "")
        npc_lines2 = (data.get("narration") or {}).get("npc_lines", [])
        choices2 = data.get("choices") or []
        trace2 = data.get("server_trace") or {}
        dm_turns.append({
            "turn": turn_num, "label": "statue examination",
            "status": resp.status_code, "session_id": session_id,
            "endpoint": trace2.get("server_endpoint_called"),
            "scene": scene2, "npc_lines": npc_lines2, "choices": choices2,
            "raw": data,
        })
        print(f"\n  Turn {turn_num} status={resp.status_code}")
        print(f"  Scene: {scene2[:300]}")
        print(f"  NPC lines: {npc_lines2}")
        if choices2:
            for i, c in enumerate(choices2, 1):
                lbl = c.get("label", c) if isinstance(c, dict) else c
                print(f"  Choice {i}: {lbl}")
        transcript.append({"step": f"dm_turn_{turn_num}", "status": resp.status_code})

        # Phase 5: Final state
        print("\n=== Phase 5: Final state ===")
        char_final = client.get(f"{RULES}/characters/{cid}").json()
        flags_final = client.get(f"{RULES}/narrative/flags/{cid}").json()
        print(f"  Location: {char_final.get('location_id')}")
        print(f"  Flags: {flags_final}")
        
        try:
            summary = client.get(f"{RULES}/narrative-introspect/character/{cid}/summary").json()
            print(f"  Endings: {[(e['ending_name'], e['is_reachable']) for e in summary.get('endings',[])]}")
        except Exception as e:
            print(f"  Summary endpoint error: {e}")
            summary = {"endings": []}

        transcript.append({"step": "final_state", "location": char_final.get("location_id"), "flags": flags_final})

    # Write artifacts
    report = {
        "timestamp": run_ts, "character": {"name": char_name, "id": cid, "class": "Fighter", "race": "Human"},
        "scenario": "A", "base_urls": {"rules": RULES, "dm": DM},
        "artifact_paths": {
            "transcript_json": str(artifact_dir / "transcript.json"),
            "dm_prose_markdown": str(artifact_dir / "dm-prose.md"),
        },
        "transcript": transcript, "final_flags": flags_final, "dm_turns": dm_turns,
    }

    with open(artifact_dir / "transcript.json", "w") as f:
        json.dump(report, f, indent=2)

    # Write dm-prose.md
    lines = [f"# D20 DM Prose Log — {char_name}", ""]
    lines.append(f"- Character ID: `{cid}`")
    lines.append(f"- Started: {run_ts}Z")
    lines.append(f"- Rules URL: {RULES}")
    lines.append(f"- DM URL: {DM}")
    lines.append("")
    for turn in dm_turns:
        lines.append(f"## Turn {turn['turn']:03d} — {turn['label']}")
        lines.append("")
        lines.append(f"**Tester message:** {{message}}")
        lines.append(f"**Status:** {turn['status']}")
        lines.append(f"**Session:** {turn.get('session_id')}")
        lines.append(f"**Endpoint called:** {turn.get('endpoint')}")
        lines.append("")
        lines.append("### DM scene")
        lines.append("")
        lines.append(turn["scene"])
        lines.append("")
        lines.append("### NPC lines")
        if turn.get("npc_lines"):
            for npc in turn["npc_lines"]:
                if isinstance(npc, dict):
                    lines.append(f"- **{npc.get('speaker','?')}:** {npc.get('text','')}")
                else:
                    lines.append(f"- {npc}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("### Choices")
        if turn.get("choices"):
            for i, c in enumerate(turn["choices"], 1):
                lbl = c.get("label", c) if isinstance(c, dict) else c
                lines.append(f"{i}. {lbl}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("### Server trace")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(turn.get("raw", {}).get("server_trace", {}), indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")

    with open(artifact_dir / "dm-prose.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n=== COMPLETE ===")
    print(f"Transcript: {artifact_dir / 'transcript.json'}")
    print(f"DM prose:   {artifact_dir / 'dm-prose.md'}")
    print(f"DM turns logged: {len(dm_turns)}")

if __name__ == "__main__":
    run()
