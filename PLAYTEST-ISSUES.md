# D20 Playtest Issues Log

**Last Reviewed:** 2026-04-23 (heartbeat init — file was missing, created from scratch)

**Open Issues:** 4 | **Fixed Issues:** 0

---

## Open Issues

### ISSUE-001: DM runtime root endpoint returns HTML instead of JSON (test mismatch)

**Severity:** P2-Medium (test fails, production landing page works)

**Repro Steps:**
1. `GET https://d20.holocronlabs.ai/` (DM runtime root)
2. Observe `Content-Type: text/html` with landing page HTML
3. Compare against `tests/test_smoke.py::test_dm_runtime_root` which expects `r.json()` to return `{"service": "d20-dm-runtime"}`

**Expected:** JSON response `{"service": "d20-dm-runtime", "status": "ok"}` (api health style)
**Actual:** 200 OK with `Content-Type: text/html` and full landing page HTML body

**Evidence:**
- Smoke test output: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` at line 137 of test_smoke.py
- Live curl: `<html>...<title>The Dreaming Hunger</title>...</html>` returned from `/`
- `/dm/health` endpoint returns proper JSON: `{"status":"healthy","dm_runtime":"ok",...}`

**Impact:** CI/cron smoke test fails (1/17). No impact on actual gameplay since landing page is correct.

**Suggested Fix:** Either:
- Change test to assert HTML content-type and check for title/heading (align with landing page reality), OR
- Add a `/api/status` or change `/` to return JSON for API consumers, keep `/` as landing page

**Mission Control Task:** (create MC task linking to this severity/fix)

**Reported:** 2026-04-23 — Hermes Heartbeat Agent
**Status:** OPEN

---

### ISSUE-002: PLAYTEST-ISSUES.md file was missing from repository

**Severity:** P3-Low (documentation gap, not runtime bug)

**Repro Steps:**
1. Attempt to read `~/Projects/rigario-d20/PLAYTEST-ISSUES.md`
2. File not found error

**Expected:** File exists per PLAYTEST-GUIDE.md specification
**Actual:** File never existed in git history (git log shows zero commits on this path)

**Impact:** No persistent issue tracking for playtest sessions. Each heartbeat agent must recreate context. Violates the "durable written evidence" requirement.

**Suggested Fix:** Create file with proper template structure (done 2026-04-23 by heartbeat agent). Add to git.

**Reported:** 2026-04-23 — Hermes Heartbeat Agent
**Status:** OPEN (file created locally; needs commit)

---

### ISSUE-003: NPC interact targeting broken — target parameter ignored, random NPC selected

**Severity:** P1-High (blocks narrative progression — cannot reliably talk to specific NPCs)

**Repro Steps:**
1. Create character (any)
2. Move to `south-road` (biome contains both Sister Drenna and Kira)
3. `POST /characters/{id}/actions` with `{"action_type": "interact", "target": "Sister Drenna"}`
4. Observe returned narration mentions a different NPC (Kira the Wagon Master)

**Expected:** Interaction with the explicitly named NPC Sister Drenna
**Actual:** Random NPC from current biome selected, ignoring the `target` field

**Evidence:**
- Endpoint: `POST /characters/gatetest-001-xxxx/actions` (action_type=interact, target="Sister Drenna")
- Status: 200
- Response excerpt: `"You approach Kira the Wagon Master (merchant)..."` (should say Sister Drenna)
- Flags set after interactions: `kira_orc_refugee_intel` (proves Kira was talked to, not Drenna)
- Character ID: `targettest-001-29a2e3` created 2026-04-23
- Timestamp: 2026-04-23T08:55:00Z (approx)

**Root Cause Hypothesis:** The interact action's target-matching loop exists (see actions.py:~1426-1435) but either:
- `body.target` is not being passed correctly from ActionRequest,
- Name comparison fails due to case/normalization mismatch,
- Or NPC list query (`WHERE biome = ?`) returns multiple rows and the match loop falls through incorrectly.

**Impact:** Blocks ALL narrative chains that require specific NPC interaction:
- Drenna quest chain (`drenna_recruited_by_kol` → `kol_backstory_known`) unreachable
- Kol backstory dialogue never triggered
- Communion ending currently locked

**Suggested Fix:** Add debug logging to print:
- `body.target` value received
- List of NPC names considered
- Whether match succeeded
And fix the name comparison (ensure both sides normalized identically).

**Reported:** 2026-04-23 — Hermes Heartbeat Agent
**Status:** OPEN

---

### ISSUE-004: Character current_location_id not updated after move action

**Severity:** P1-High (breaks location-gated content, quests, and narrative state)

**Repro Steps:**
1. Create character
2. Call `POST /characters/{id}/actions` with `{"action_type": "explore"}` (sets location to Thornhold?)
3. Call `POST /characters/{id}/actions` with `{"action_type": "move", "target": "south-road"}`
4. `GET /characters/{id}` and inspect `current_location_id`

**Expected:** `current_location_id` updates to `south-road` after successful move narration
**Actual:** `current_location_id` remains `None` (null) in character record

**Evidence:**
- After explore: response narration indicates Thornhold statue, but `current_location_id` is `None`
- After move to south-road: narration says "You travel to South Road...", yet `current_location_id` is still `None`
- Character ID: `targettest-001-29a2e3`, 2026-04-23
- Endpoint: `GET /characters/{id}` returns `"current_location_id": null`

**Root Cause Hypothesis:** The `move` action handler likely calls `_log_event` and updates game time but does not actually update the `characters.current_location_id` field in the DB. The location context is derived from the event log instead of being persisted on character row.

**Impact:**
- Any location-gated encounter/flag may fail (e.g., puzzle prerequisites that check `character.current_location_id`)
- World state appears inconsistent between narration and DB
- Could cause quest acceptance/advancement bugs if location is verified

**Suggested Fix:** In `submit_action` → `move` branch, after successful move:
```python
conn.execute("UPDATE characters SET current_location_id = ? WHERE id = ?", (target_location_id, character_id))
```

**Reported:** 2026-04-23 — Hermes Heartbeat Agent
**Status:** OPEN

---

## Fixed Issues

*(none)*

---

## Playtest Session Reports

### 2026-04-23 08:45–10:30 UTC — Heartbeat Agent — Scenarios A (smoke), A (full), targeting/location validation

**Smoke Test:** 16/17 PASS
- **FAILURE:** `test_dm_runtime_root` (ISSUE-001) — DM `/` returns HTML, test expects JSON
- All other rules + DM tests passed (character CRUD, explore, combat, DM turn, persistence, cadence)

**Playtest Scenario:** A (Character Creation + First Steps) — FULL RUN

**Character:** `GateTest-507924` (Fighter Human, ID: `gatetest-507924-2b7060`)
- Created: 2026-04-23T08:46:28Z
- Location progression: Thornhold → South Road (narration only; location persistence bug)
- Final flags: `thornhold_statue_observed=1`

**Transcript (condensed):**
| Step | Endpoint | Status | Evidence |
|------|----------|--------|----------|
| Character create | `POST /characters` | 201 | `{"id":"gatetest-...","name":"GateTest-507924"...}` |
| Explore Thornhold | `POST /characters/{id}/actions` (explore) | 200 | `"You search Thornhold but find nothing of value. You glance at the statue..."` |
| DM turn (explore) | `POST /dm/turn` | 200 | `"scene": "You search Thornhold but find nothing of value."` |
| Get flags | `GET /narrative/flags/{id}` | 200 | `{"thornhold_statue_observed":"1"}` |
| Get summary | `GET /narrative-introspect/character/{id}/summary` | 200 | `mark_stage:0, location:null` |

**Additional Validation — Drenna quest chain attempt:**
- Move to south-road: 200 OK (narration confirms travel, but `current_location_id` remains `None` — ISSUE-004)
- Interact target="Sister Drenna": **BUG** — returned Kira dialogue instead (ISSUE-003)
- Quest accept `quest-save-drenna-child`: 200 OK — quest action functional; quest definition exists on Sister Drenna NPC

**Critical Issues Discovered & Reproduced:**
- ISSUE-001: DM root test mismatch (verified smoke test failure)
- ISSUE-003: NPC interact targeting broken — target field ignored, random NPC selected from biome
- ISSUE-004: Character location not persisted after move actions

**Issues Not Reproduced:** N/A (all open issues newly discovered this run)

**New Issues Created:** ISSUE-003, ISSUE-004 (added to PLAYTEST-ISSUES.md)

**Notes:**
- The narrative chain for Communion (`kol_backstory_known` → `kol_ally`) is currently **unreachable** due to ISSUE-003 preventing reliable interaction with Sister Drenna to obtain that flag.
- Quest acceptance (`quest` action type) works correctly when the quest ID matches the NPC's defined `quests_json`.
- Recommend immediate fix on ISSUE-003 (targeting) as highest-priority — it blocks Phase 1 narrative completion.
- Smoke test failure (ISSUE-001) is P2; should align test expectations with actual production endpoint behavior.

---

## Template for New Issues

> **Category:** Combat | Narrative | Technical | UX
> **Reproduces:** YES / NO / PARTIAL
> 
> **Steps:** 1. ... 2. ...
> **Expected:** ...
> **Actual:** ...
> 
> **Evidence:**
> - Endpoint: ...
> - Status: ...
> - Character ID: ...
> - Timestamp: ...
