# D20 Playtest Guide — "The Dreaming Hunger"

**Project:** Rigario D20 Agent RPG
**Status:** Active Playtest
**Last Updated:** 2026-04-24
**Maintainer:** Hermes Agent (heartbeat)
**Source Docs:** PLAYTEST-RUNBOOK.md, PLAYTEST-PLAN.md, NARRATIVE-MAP.md

---

## Quick Start

This guide is self-contained. An agent reading ONLY this document should understand:
1. What the game is and how it works
2. The complete narrative arc and endings
3. How to run a playtest from start to finish
4. What evidence to capture and how to report issues

## 1. What Is This Game?

### Core Promise

"Install once. Your agent plays your D&D character 24/7. You only step in when it matters."

The D20 Agent RPG is a persistent, AI-driven D&D 5E campaign where:
- **Player agents** (your AI) control character actions, choices, and level-ups
- **DM agent** (our AI) narrates the world, voices NPCs, and presents tactical choices
- **Server** (rules engine) validates all 5E mechanics, stores state, manages combat
- **Human** sets strategic direction, approves at checkpoints, reviews story

### The Three-Entity Model

```
Player Agent (yours)          DM Agent (ours)          Server (referee)
───────────────                ─────────────            ──────────────
Creates character ──────────→ Narrates arrival       Validates rules
Makes choices ─────────────→ Voices NPCs           Stores state
Submits actions ──────────→ Presents choices      Manages combat
                            ←────────────────────  Returns context
```

**Key invariant:** Server is authoritative. DM and Player agents both talk to the server. The server never talks back to DM directly — only through structured responses.

## 2. The Story — "The Dreaming Hunger"

### Setting

Thornhold, a dying town on the edge of Whisperwood forest. An ancient entity, The Dreaming Hunger, seeps through a weakening seal. The player is marked with the **Mark of the Dreamer** — a sigil that attracts supernatural attention.

### Five-Act Narrative Arc

| Act | Stage | Key Event | Required Flag | Location |
|-----|-------|-----------|---------------|----------|
| 1 | Statue Gate | Examine Thornhold statue | `thornhold_statue_observed` | thornhold |
| 2 | Puzzle Gate | Solve antechamber puzzle (alignment-based) | `antechamber_solved` | antechamber |
| 3 | Combat Chain | Defeat 3 encounter waves (forest-edge, deep-forest, crossroads) | `portent_2/3/4_triggered` | various |
| 4 | Quest Gate | Talk to Sister Drenna → get confession → talk to Brother Kol | `kol_backstory_known` | roads/cave-depths |
| 5 | Climax | Confront The Dreaming Hunger (cave-depths) | `hunger_confronted` | cave-depths |

### Three Endings

| Ending | Unlock Condition | Final Flag |
|--------|-----------------|------------|
| **Reseal** | Standard completion, no special prep | `ending_reseal` |
| **Merge** | Player has taken significant Dream-power risks (e.g. 3+ Mark uses) | `ending_merge` |
| **Communion** | Complete Kol backstory chain (Drenna → Kol confession) AND have `kol_ally` | `ending_communion` |

**Note:** Communion is currently BLOCKED — world geography prevents reaching Drenna/Kol (see ISSUE-013).

## 3. The Mark System (The Dreamer's Sigil)

The Mark progresses through Stages 0 → 1 → 2 → 3+.

| Stage | Uses Remaining | Effect |
|-------|---------------|--------|
| 0 | 3 | Freshly marked; minimal influence |
| 1 | 2 | Dream-whispers at edges of perception |
| 2 | 1 | Visions intensify; NPCs react uneasily |
| 3+ | 0 | Mark fully spent — The Hunger notices you |

**Suppression Mechanic:** The Mark can be suppressed through ritual/rest. Once uses reach 0, narrative effects intensify automatically. Track via `mark_stage` flag.

## 4. Fronts — The Dreaming Hunger (Doom Clock)

The Front advances as you defeat encounters in key locations. Each victory triggers the next Grim Portent.

| Stage | Grim Portent | Trigger Condition | Narrative Flag |
|-------|-------------|-------------------|----------------|
| 0 | The First Mark | Del encounter completes | `del_encounter_fired` |
| 1 | Animals Dying | Combat victory at forest-edge | `portent_2_triggered` |
| 2 | Undead Walk | Combat victory at deep-forest | `portent_3_triggered` |
| 3 | Seal Weeps | Combat victory at crossroads | `portent_4_triggered` |
| 4 | Breaking Rite | Combat victory at cave-entrance | `portent_5_triggered` |
| 5 | Hunger Speaks | Combat victory at cave-depths | `portent_6_triggered` |
| 6 | The Door Opens | (Auto-advance after stage 5) | — |
| 7 | The Feast Begins | (Auto-advance after stage 6) | — |

**Impending Doom:** The Dreaming Hunger breaks free. The seal shatters. The world dreams no more.

## 5. How to Playtest

### Primary Testing Mode — DM-Agent First

All playtests now target the **live DM agent path** first. The testing agent should behave like a player: send natural-language intent to `POST /dm/turn`, evaluate the DM's narration/choices, and only use direct rules endpoints as diagnostic controls.

Required order for every narrative beat:
1. **DM path first:** `POST /dm/turn` with the player's intent.
2. **Full prose capture:** write the complete DM response to a durable transcript file before summarizing or truncating anything.
3. **State verification:** call rules endpoints (`GET /characters/{id}`, `GET /narrative/flags/{id}`, combat endpoints) to verify the DM narration matches authoritative state.
4. **Direct action fallback only for diagnosis:** if `/dm/turn` fails or misroutes, call `POST /characters/{id}/actions` with the equivalent structured action to isolate whether the bug is in DM routing/synthesis or the rules layer.

Do **not** treat a direct action success as playtest success unless the DM-agent path also works. The product experience is the DM agent.

### Mandatory DM Prose Logging

The testing agent must fully log what the DM agent says into a reviewable file for narrative/prose review.

Required files per run:
- Machine-readable full transcript: `playtest-runs/<timestamp>-<character_id>/transcript.json`
- Human-readable prose log: `playtest-runs/<timestamp>-<character_id>/dm-prose.md`

`dm-prose.md` must include, for every `/dm/turn`:
- Turn number and timestamp
- Character ID and current location when known
- Exact player/tester message sent to the DM
- HTTP status and Hermes `session_id`
- Full `narration.scene` text with **no truncation**
- Full `narration.npc_lines` text with speaker names
- Full visible `choices` labels
- Relevant mechanics summary and `server_trace.server_endpoint_called`
- Any mismatch notes from the verifier

Short excerpts may go in `PLAYTEST-ISSUES.md`, but prose review requires the full `dm-prose.md` file.

### Prerequisites

- Production endpoints: `https://d20.holocronlabs.ai` (rules: :8600, DM: :8610)
- Test character: fresh character per scenario (avoid cross-contamination)
- Playtest harness: `scripts/full_playthrough_with_gates.py` (recommended; writes full DM prose logs)
- Session report: always append to `PLAYTEST-ISSUES.md`

### Character Build Recommendations

For consistent combat testing:
- **Class:** Fighter (Battle Master) or Wizard (School of Evocation)
- **Race:** Human (variant) or Dwarf (Hill)
- **Stats:** Standard array (15/14/13/12/10/8) or point-buy 27
- **Background:** Soldier or Sage (for narrative hooks)

### Five Test Scenarios

Each scenario exercises a different narrative/mechanical path. In every scenario, the testing agent must drive the beat through `/dm/turn` first and then verify state mechanically.

**Scenario A — Character Creation + First Steps**
- Create character → ask DM to look around Thornhold → ask DM to examine the statue
- Verify: `thornhold_statue_observed` flag set, DM narration references statue, `dm-prose.md` contains full opening and statue prose
- Direct action fallback: `explore` only if DM path fails or needs isolation
- Gate: Statue acknowledgment

**Scenario B — Absurd/AI Stress Test**
- Send impossible DM-agent intents: "I swallow the statue", "I fly to the moon"
- Verify: DM refuses gracefully, asks for clarification or constrains action, and does not misroute as movement
- Log full refusal prose in `dm-prose.md` for tone review
- Gate: None (observation only)

**Scenario C — Combat Full Chain**
- Use DM-agent natural language to travel toward danger, trigger encounter, and choose combat tactics
- Verify: `choices` array populated, HP damage tracked, combat log updated, DM combat prose is legible and tactically actionable
- Direct combat endpoints only diagnose failures after DM path evidence is captured
- Gate: Combat tactic choice (Attack/Flee/Cast/Defend)

**Scenario D — NPC Quest Chain**
- Use DM-agent dialogue to find Sister Drenna, accept quest, find Brother Kol, and learn backstory
- Verify: `kol_backstory_known` flag set after dialogue chain and DM prose preserves NPC voice/continuity
- Direct quest/action endpoints only diagnose missing flags after DM dialogue is logged
- Gate: Quest acceptance (Accept/Refuse/Arrest), Kol fate choice (Fight/Persuade/Commune)

**Scenario E — Portal / Ending Access**
- Use DM-agent narration to reach cave-depths and trigger climax/ending choice
- Verify: POST `/portal/token` returns 201 with token, GET `/portal/{token}/state/view` renders sheet, ending prose is fully captured
- Gate: Ending choice (Reseal/Merge/Commune)

**Rotation order for unattended runs:** A → B → C → D → E → (repeat)

## 6. What to Capture — Session Log Template

Every run must produce both a structured transcript and a prose review file.

```json
{
  "timestamp": "2026-04-24T10:30:00Z",
  "character": {
    "name": "Playtest-XYZ",
    "id": "char-uuid",
    "class": "Fighter", "race": "Human"
  },
  "scenario": "C",
  "base_urls": {
    "rules": "https://d20.holocronlabs.ai",
    "dm": "https://d20.holocronlabs.ai"
  },
  "artifact_paths": {
    "transcript_json": "playtest-runs/20260424T103000Z-char-uuid/transcript.json",
    "dm_prose_markdown": "playtest-runs/20260424T103000Z-char-uuid/dm-prose.md"
  },
  "smoke_test": "17/17 PASS",
  "transcript": [
    {"kind": "create", "endpoint": "/characters", "status": 201, "evidence": "..."},
    {
      "kind": "dm_turn",
      "endpoint": "/dm/turn",
      "status": 200,
      "turn_number": 1,
      "message": "I look around Thornhold.",
      "session_id": "20260424_...",
      "full_response_logged": true,
      "prose_log_anchor": "turn-001"
    },
    {"kind": "verify_state", "endpoint": "/characters/{id}", "status": 200, "location_id": "thornhold"}
  ],
  "final_flags": {
    "thornhold_statue_observed": "1",
    "antechamber_solved": "1"
  },
  "reproduced_issues": ["ISSUE-001", "ISSUE-003"],
  "notes": "Combat choices worked; Kol geography blocked"
}
```

`dm-prose.md` should be readable by Rigario without opening JSON. Example turn block:

```markdown
## Turn 001 — 2026-04-24T10:30:00Z

**Tester message:** I look around Thornhold.
**Status:** 200
**Session:** 20260424_...
**Location before:** thornhold
**Endpoint called:** actions

### DM scene
<full narration.scene, untruncated>

### NPC lines
- **Aldric:** <full line>

### Choices
1. <full visible label>
2. <full visible label>

### Verifier notes
- State check: location_id=thornhold
- Mismatch: none
```

## 7. How to Report Issues

### Severity Definitions

| Level | Meaning | Response Time |
|-------|---------|---------------|
| P1-High | Blocks narrative arc or core loop | Fix before next playtest |
| P2-Medium | Functional gap, workaround exists | Fix before Phase 2 |
| P3-Low | Polish / nice-to-have | Fix before Phase 3 |

### Report Format

**Step 1:** Search `PLAYTEST-ISSUES.md` for matching issue.
**Step 2:** If found, append dated evidence under existing ISSUE entry.
**Step 3:** If new, add entry in Open Issues before the `---\n\n## Fixed Issues` separator using next sequential number (ISSUE-XXX).
**Step 4:** Append a session report in `## Playtest Session Reports` section.

**Evidence requirements:**
- Endpoint + HTTP status
- One line of response excerpt in `PLAYTEST-ISSUES.md`
- Character ID + scenario
- Timestamp
- Path to full prose log (`dm-prose.md`) whenever a DM narrative issue or prose-quality finding is reported
- For DM issues: include the exact turn number from `dm-prose.md`, not just a summary

### Issue Type Cheat Sheet

| Category | Typical Triggers |
|----------|-----------------|
| Combat | Empty choices, missing damage, turn order bugs |
| Narrative | Flags not set, NPC unreachable, ending blocked |
| Technical | 404/500 errors, schema nulls, DB errors |
| UX | Confusing responses, missing choices, unclear gates |

## 8. Quick Reference — Key Endpoints

| Purpose | Endpoint | Method | Notes |
|---------|----------|--------|-------|
| Character creation | `/characters` | POST | JSON body with name/race/class/stats |
| Get character | `/characters/{id}` | GET | Schema: nested armor_class, hp, classes |
| Direct action | `/characters/{id}/actions` | POST | `explore`, `move`, `rest`, `quest` |
| DM turn | `/dm/turn` | POST | `{character_id, message}` → narration + choices |
| Combat state | `/characters/{id}/combat` | GET | Active combat session info |
| Combat action | `/characters/{id}/combat/act` | POST | `{action, target_index, d20_roll}` |
| Flags | `/narrative/flags/{id}` | GET | Dict of all narrative flags |
| Summary | `/narrative-introspect/character/{id}/summary` | GET | Ending availability, front progress |
| Health check | `/health` (rules) `/dm/health` (dm) | GET | 200 with status JSON |
| Portal token | `/portal/token` | POST | Creates share token for player portal |
| Portal view | `/portal/{token}/state/view` | GET | Renders character sheet HTML |

**Production base:** `https://d20.holocronlabs.ai`

## 9. The Big Picture — Roadmap

### Phase 1: Core Loop Complete (Target: May 3, 2026 — Hackathon Deadline)
- All 3 endings reachable
- Combat choices populate and damage applies
- World geography fully connected (all 9 locations reachable)
- Portal token generation functional
- Smoke test: 17/17 PASS

### Phase 2: Polish & Persistence
- Save/load character across server restarts
- Multi-session campaign with checkpoints
- Agent delegation framework integration

### Phase 3: Scale & Share
- Multi-campaign support
- Human dashboard (Portal enhancements)
- Agent marketplace (premade character agents)

---

## Appendix: Links

- Source runbook: `PLAYTEST-RUNBOOK.md`
- Test scenarios: `PLAYTEST-PLAN.md` (detailed)
- Narrative structure: `NARRATIVE-MAP.md`
- Architecture: `ARCHITECTURE.md` + `DM-RUNTIME-ARCHITECTURE.md`
- Issues log: `PLAYTEST-ISSUES.md` (append session reports here)
- Player portal spec: `PLAYER-PORTAL-SPEC.md`
- Hackathon submission: `SUBMISSION.md`

---

*This guide was auto-synthesized from source documents on 2026-04-23 for automated playtest agent consumption.*
