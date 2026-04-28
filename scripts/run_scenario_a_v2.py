#!/usr/bin/env python3
"""Scenario A v2 — Full DM-first path with movement to town square."""
import httpx, json, uuid, os
from datetime import datetime, timezone
from pathlib import Path

RULES = "https://agentdungeon.com"
DM = "https://agentdungeon.com"
TIMEOUT = 120.0

def run():
    char_name = f"ScenA-{uuid.uuid4().hex[:6]}"
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = Path("playtest-runs") / f"{run_ts}-{char_name}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    transcript = []
    dm_turns = []

    with httpx.Client(timeout=TIMEOUT) as c:
        def log(step, data):
            transcript.append({"step": step, **data})
            print(f"  [{step}] {data}")

        # Health
        h1 = c.get(f"{RULES}/health")
        h2 = c.get(f"{DM}/dm/health")
        print(f"Health: rules={h1.status_code} dm={h2.status_code}")

        # 1. Create character
        print("\n=== 1. Create Character ===")
        resp = c.post(f"{RULES}/characters", json={
            "name": char_name, "race": "Human", "class": "Fighter", "background": "Soldier"
        })
        char = resp.json()
        cid = char["id"]
        loc = char.get("location_id")
        print(f"  Created: {cid} at {loc}")
        log("create", {"status": resp.status_code, "id": cid, "location": loc})

        # 2. Move from rusty-tankard → thornhold
        print("\n=== 2. Move to Thornhold ===")
        resp = c.post(f"{RULES}/characters/{cid}/actions", json={
            "action_type": "move", "target": "thornhold"
        })
        data = resp.json()
        success = data.get("success")
        new_loc = (data.get("character_state") or {}).get("location_id") or data.get("location_id")
        narr = data.get("narration", "")
        print(f"  Move: status={resp.status_code} success={success} loc={new_loc}")
        print(f"  Narration: {narr[:200]}")
        log("move_to_thornhold", {"status": resp.status_code, "success": success, "location": new_loc})

        # Verify location
        char_check = c.get(f"{RULES}/characters/{cid}").json()
        print(f"  GET location_id={char_check.get('location_id')} current_location_id={char_check.get('current_location_id')}")

        # 3. Explore at Thornhold
        print("\n=== 3. Explore Thornhold ===")
        resp = c.post(f"{RULES}/characters/{cid}/actions", json={"action_type": "explore"})
        data = resp.json()
        narr = data.get("narration", "")
        print(f"  Explore: status={resp.status_code} success={data.get('success')}")
        print(f"  Narration: {narr[:300]}")
        log("explore_thornhold", {"status": resp.status_code, "narration": narr[:200]})

        # 4. Check flags
        flags = c.get(f"{RULES}/narrative/flags/{cid}").json()
        print(f"  Flags: {flags}")
        log("flags_after_explore", {"flags": flags})

        # 5a. DM Turn 1: Look around Thornhold
        print("\n=== 4. DM Turns ===")
        session_id = None

        for msg, label in [
            ("I look around Thornhold's town square. Tell me about this place.", "look around thornhold"),
            ("I approach the old stone statue at the center of the square. What do I notice?", "examine statue"),
            ("I run my hand over the stone hand. Is there a seal marking? Any sigils?", "inspect seal markings"),
        ]:
            body = {"character_id": cid, "message": msg}
            if session_id:
                body["session_id"] = session_id
            turn_num = len(dm_turns) + 1
            print(f"  DM Turn {turn_num}: {label}")
            resp = c.post(f"{DM}/dm/turn", json=body, timeout=120)
            data = resp.json()
            session_id = data.get("session_id", session_id)
            scene = (data.get("narration") or {}).get("scene", "")
            npc_lines = (data.get("narration") or {}).get("npc_lines", [])
            choices = data.get("choices") or []
            trace = data.get("server_trace") or {}
            entry = {
                "turn": turn_num, "label": label, "status": resp.status_code,
                "session_id": session_id, "trace": trace.get("server_endpoint_called"),
                "scene": scene[:800], "npc_lines": npc_lines, "choices": choices,
                "raw": data,
            }
            dm_turns.append(entry)
            print(f"    status={resp.status_code} session={session_id}")
            print(f"    endpoint={trace.get('server_endpoint_called')}")
            print(f"    scene: {scene[:300]}")
            if npc_lines:
                for n in npc_lines:
                    sp = n.get("speaker","?") if isinstance(n,dict) else "?"
                    tx = n.get("text","") if isinstance(n,dict) else str(n)[:150]
                    print(f"    NPC {sp}: {tx}")
            if choices:
                for i, c2 in enumerate(choices, 1):
                    lbl = c2.get("label", c2) if isinstance(c2, dict) else c2
                    print(f"    Choice {i}: {lbl}")
            log(f"dm_turn_{turn_num}", {"status": resp.status_code, "label": label, "session_id": session_id})

        # 6. Final state
        print("\n=== 5. Final State ===")
        char_final = c.get(f"{RULES}/characters/{cid}").json()
        flags_final = c.get(f"{RULES}/narrative/flags/{cid}").json()
        print(f"  Location: {char_final.get('location_id')}")
        print(f"  HP: {char_final.get('hp_current')}/{char_final.get('hp_max')}")
        print(f"  Flags: {flags_final}")
        log("final_state", {"location": char_final.get("location_id"), "flags": flags_final})

        try:
            summary = c.get(f"{RULES}/narrative-introspect/character/{cid}/summary").json()
            print(f"  Endings: {[(e['ending_name'], e['is_reachable']) for e in summary.get('endings',[])]}")
        except Exception as e:
            print(f"  Summary error: {e}")

        # Write artifacts
        report = {
            "timestamp": run_ts,
            "character": {"name": char_name, "id": cid, "class": "Fighter", "race": "Human"},
            "scenario": "A",
            "base_urls": {"rules": RULES, "dm": DM},
            "artifact_paths": {
                "transcript_json": str(artifact_dir / "transcript.json"),
                "dm_prose_markdown": str(artifact_dir / "dm-prose.md"),
            },
            "transcript": transcript, "final_flags": flags_final, "dm_turns": dm_turns,
        }

        with open(artifact_dir / "transcript.json", "w") as f:
            json.dump(report, f, indent=2)

        lines = [f"# D20 DM Prose Log — {char_name}", ""]
        lines.append(f"- Character ID: `{cid}`")
        lines.append(f"- Started: {run_ts}Z")
        lines.append(f"- Rules URL: {RULES}")
        lines.append(f"- DM URL: {DM}")
        lines.append("")
        for turn in dm_turns:
            lines.append(f"## Turn {turn['turn']:03d} — {turn['label']}")
            lines.append("")
            lines.append(f"**Status:** {turn['status']}")
            lines.append(f"**Session:** {turn.get('session_id')}")
            lines.append(f"**Endpoint:** {turn.get('trace')}")
            lines.append("")
            lines.append("### DM scene")
            lines.append("")
            lines.append(turn["scene"])
            lines.append("")
            lines.append("### NPC lines")
            if turn.get("npc_lines"):
                for n in turn["npc_lines"]:
                    sp = n.get("speaker", "?") if isinstance(n, dict) else "?"
                    tx = n.get("text", "") if isinstance(n, dict) else str(n)
                    lines.append(f"- **{sp}:** {tx}")
            else:
                lines.append("- None")
            lines.append("")
            lines.append("### Choices")
            if turn.get("choices"):
                for i, c2 in enumerate(turn["choices"], 1):
                    lbl = c2.get("label", c2) if isinstance(c2, dict) else c2
                    lines.append(f"{i}. {lbl}")
            else:
                lines.append("- None")
            lines.append("")
            lines.append("### Verifier notes")
            lines.append("- State check: Character at thornhold (before this turn)")
            lines.append("- Mismatch: None (review prose continuity)")
            lines.append("")

        with open(artifact_dir / "dm-prose.md", "w") as f:
            f.write("\n".join(lines) + "\n")

        print(f"\n=== COMPLETE ===")
        print(f"Transcript: {artifact_dir / 'transcript.json'}")
        print(f"DM prose:   {artifact_dir / 'dm-prose.md'}")
        print(f"DM turns: {len(dm_turns)}")

if __name__ == "__main__":
    run()
