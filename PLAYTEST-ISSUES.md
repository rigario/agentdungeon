# D20 Playtest Issues Log

**Last Reviewed:** 2026-04-23 07:42 UTC — Heartbeat — Scenario A run

**Open Issues:** 4 | **Fixed Issues:** 5
---

## Open Issues

### ISSUE-006: DM narration returns wrong NPC content for statue examination

**Severity:** P2-Medium  (narrative degradation; core loop functions)
**Category:** Narrative  (DM synthesis)
**Reproduces:** YES
**Discovered:** 2026-04-23 — Heartbeat agent, Scenario A

**Steps:**
1. Create character (Fighter Human) — ID: `playtest-a-20260423023553-49b486`
2. POST `/characters/{id}/actions` explore Thornhold (sets `thornhold_statue_observed` = 1)
3. POST `/dm/turn` with message: "I examine the statue carefully. What do I see?"

**Expected:** DM narration describes the stone statue in the town square, pointing NE, seal symbols on hand
**Actual:** DM returns Marta the Merchant dialogue: "You approach Marta the Merchant (merchant). Looking to buy or sell? I've got fair prices."

**Evidence:**
- Endpoint: `/dm/turn`
- Status: 200
- Character ID: `playtest-a-20260423023553-49b486`
- Timestamp: 2026-04-23T02:37:48Z
- `server_trace.intent_used.type`: `interact`  (routing CORRECT)
- `server_trace.intent_used.target`: `"statue carefully"`  (target intact)
- `narration.scene`: `"You approach Marta the Merchant (merchant). Looking to buy or sell?"`  (WRONG)

**Analysis:** Intent router correctly identifies `interact` target `"statue"`, but synthesis layer returns cached/default exploration dialogue for Marta instead of statue-specific content. Independent of ISSUE-003 (targeting) — target string reaches synthesis layer intact.

**MC Task:** TODO — Investigate `dm-runtime/app/services/synthesis.py` narrative selection logic


**Heartbeat Check (2026-04-23 03:37 UTC):**
- Status: NOT REPRODUCED in Scenario B run
- Narration: "You approach Ser Maren (guard). State your business in Thornhold." (correct NPC)
- Action: ISSUE-006 remains OPEN — intermittent? requires deeper synthesis inspection


**Heartbeat Check (2026-04-23 04:51 UTC — Scenario C):**
- Condition: Not tested (scenario did not reach statue-examination stage due to harness crash)
- Status: ISSUE-006 remains OPEN — intermittent; still unverified


**Heartbeat Check (2026-04-23 05:43 UTC — Isolated):**
- Condition: Isolated statue-examination test with fresh character at south-road
- Status: CONFIRMED — DM returned Ser Maren (guard) dialogue instead of statue description
- Evidence: Endpoint `/dm/turn`, status=200, char ID `hb-d-stat-...`; intent.type=interact, target="statue carefully"; narration.scene="You approach Ser Maren (guard) ..."


**Heartbeat Check (2026-04-23 06:45 UTC — Scenario E):**
- Condition: Full playtest run, character reached cave-depths, statue examine attempted
- Status: CONFIRMED — DM returned wrong NPC (Ser Maren guard) instead of statue description
- Evidence: `/dm/turn` status=200, char ID `scenarioe-1776926233-a5caae`, target="statue carefully", narration.scene="You approach Ser Maren (guard)..."
**Heartbeat Check (2026-04-23 07:43 UTC — Scenario A):**
- Condition: Fresh character, explore Thornhold, DM turn statue examination
- Status: CONFIRMED — DM returned Marta the Merchant dialogue (wrong NPC)
- Evidence: `/dm/turn` status=200, char ID `hb-scena-1776929801-1b2699-473423`, target="statue carefully", narration.scene="You approach Marta the Merchant (merchant). Looking to buy or sell?"

### ISSUE-007: Location persistence regression after move action (P1-High)

**Severity:** P1-High  (blocks world model, quest/NPC access)
**Category:** Persistence  (character state)
**Reproduces:** YES — Scenario B heartbeat 2026-04-23 03:37 UTC
**Discovered:** 2026-04-23 03:37 UTC — Heartbeat agent

**Steps:**
1. Create character `hb-scenb-20260423033657-db080c`
2. Explore until `thornhold_statue_observed=1`  (location: Thornhold)
3. POST `/characters/{id}/actions` move target=`south-road` (status 200)
4. GET `/characters/{id}` — `current_location_id` is `None`

**Expected:** `"current_location_id": "south-road"`
**Actual:** `"current_location_id": null`

**Evidence:**
- Move action returned 200 with narration mentioning south-road
- GET `/characters/{id}` returned `"current_location_id": null` after move
- Final character state showed `location=None`

**Analysis:** Likely regression of previously-fixed ISSUE-004. Move handler may not commit transaction or update correct field. Check `_resolve_move` return path vs character.update() call.

**MC Task:** TODO — Trace character.update() in move action handler; verify ORM session flush

**Heartbeat Check (2026-04-23 04:51 UTC — Scenario C):**
- Tested 3 move cycles (create → move south-road → move thornhold → move south-road)
- Result: location persisted correctly each time (`location_id` matched target)
- Status: ISSUE-007 NOT REPRODUCED on production with fresh character; may have been transient or specific to previous character state




**Heartbeat Check (2026-04-23 05:43 UTC — Scenario D):**
- Tested location persistence across 6 moves: thornhold→south-road→forest-edge→deep-forest→cave-entrance→cave-depths
- Each move verified via GET location_id; all matched target (no nulls observed)
- Status: ISSUE-007 remains NOT REPRODUCED — location persistence working correctly


**Heartbeat Check (2026-04-23 06:45 UTC — Scenario E):**
- Condition: Verified location persistence across 8 moves (south-road<->thornhold->forest-edge->deep-forest->cave-entrance->cave-depths)
- Status: NOT REPRODUCED — character location persisted correctly after every move; `location_id` matched expected target; no nulls observed

**Heartbeat Check (2026-04-23 07:43 UTC — Scenario A):**
- Condition: Character creation → explore → move sequence; verified both `location_id` and `current_location_id` after each step
- Status: CONFIRMED — `location_id` updates correctly (thornhold → south-road), but `current_location_id` remains `None` across all states (creation, after explore, after move). Field never populated in GET response.
- Evidence: GET after create: `current_location_id=None`; GET after move: `current_location_id=None` (while `location_id='south-road'`). Field-level bug persists.

### ISSUE-008: full_playthrough_with_gates.py crashes due to invalid location ID and missing success validation (P1-High)

**Severity:** P1-High  (blocks automated Scenario C/D/E playtest runs)
**Category:** Technical  (playtest harness)
**Reproduces:** YES
**Discovered:** 2026-04-23 — Heartbeat agent, Scenario C attempt

**Steps:**
1. Run `scripts/full_playthrough_with_gates.py` with CONTINUE=1 against production
2. Script reaches phase_antechamber_puzzle, attempts `move target="cave-entrance"`
3. API returns 200 with `"success": false` (location unreachable from current biome)
4. Script unconditionally sets `state.location_id = "cave-entrance"` (line ~141), ignoring actual response
5. DM turn "I head toward the cave entrance" routes narrative to forest-edge (state mismatch)
6. Next phase phase_south_road_wolves calls `do_action(..., target="south-rd")`
7. `south-rd` is invalid — server returns 404 "Location not found: south-rd"
8. `raise_for_status()` raises HTTPStatusError, script crashes

**Expected:** Script should (a) check `response.json().get('success')` before updating state.location_id, or derive location from `response['character_state']['location_id']`, and use only canonical location IDs. Target string must be `south-road`, not `south-rd`.

**Actual:** Uncaught httpx.HTTPStatusError, full playthrough aborts before Scenario C combat.

**Evidence:**
- Endpoint: `/characters/{char_id}/actions` (move to south-rd)
- Status: 404
- Character at crash: `gatetest-c27415-a5838c`
- Timestamp: 2026-04-23T04:46:47Z
- Traceback: `Client error '404 Not Found' for url '.../characters/gatetest-c27415-a5838c/actions'`
- Verification: location IDs confirmed via production — `south-road` valid, `south-rd` returns 404

**Analysis:** Two independent harness defects:
- Line 172: hardcoded `"south-rd"` is not a canonical location ID (should be `"south-road"`)
- Lines ~139-142: unconditional `state.location_id = ...` ignores API `success` flag, leading to corrupt world state when move fails

**MC Task:** TODO — Repair `scripts/full_playthrough_with_gates.py`: (a) replace `"south-rd"` → `"south-road"`, (b) update `state.location_id` from response `character_state.location_id` or refresh via GET after each action, (c) fail gracefully on `success=false` with DM routing.

**Heartbeat Check (2026-04-23 04:50 UTC):**
- Confirmed: move to cave-entraction returns success=false while script would overwrite state.location_id
- Confirmed: south-rd returns 404; canonical ID is south-road
- Action: ISSUE-008 created; harness repair required before next automated Scenario C run



**Heartbeat Check (2026-04-23 06:45 UTC — Scenario E):**
- Condition: Scenario E executed via direct API calls (bypassing broken harness)
- Status: Harness remains broken — production endpoints functional; script errors unrelated to server

### ISSUE-009: POST /portal/token returns 500 Internal Server Error (P1-High)

**Severity:** P1-High  (blocks Scenario E completion, portal sharing)
**Category:** Technical  (endpoint/DB)
**Reproduces:** YES
**Discovered:** 2026-04-23 06:45 UTC — Heartbeat agent, Scenario E

**Steps:**
1. Create character — ID: `scenarioe-1776926233-a5caae`
2. POST `/portal/token` with `{"character_id": "scenarioe-1776926233-a5caae"}`
3. Observe response status and body

**Expected:** 201 Created with token object containing `token`, `character_id`, `character_name`
**Actual:** 500 Internal Server Error (plain text "Internal Server Error")

**Evidence:**
- Endpoint: `/portal/token`
- Status: 500
- Character ID: `scenarioe-1776926233-a5caae`
- Timestamp: 2026-04-23 06:45 UTC
- Response excerpt: "Internal Server Error"
- Character verified: GET `/characters/scenarioe-1776926233-a5caae` returns 200 with valid sheet

**Analysis:** Likely causes: (a) `share_tokens` table missing in production DB, (b) foreign key constraint violation (character not found at token creation), or (c) unhandled exception in `create_share_token()` (portal.py). Smoke tests currently do not cover portal token generation.

**MC Task:** Check production VPS logs for traceback; verify `share_tokens` table exists with correct schema; add smoke test for `/portal/token`.

**Heartbeat Check (2026-04-23 07:43 UTC — Scenario A):**
- Condition: POST `/portal/token` with valid character ID from Scenario A run
- Status: NOT REPRODUCED — endpoint returns 201 Created with token object (issue appears resolved)
- Evidence: POST `/portal/token` status=201; response excerpt: `{"id":"...","token":"KPsvB6...","character_id":"hb-scena-1776929801-1b2699-473423"}`; character verified via GET 200

---

### ISSUE-001: DM runtime root endpoint returns HTML instead of JSON (test mismatch)
**Fixed:** 2026-04-23 — Smoke test updated to check `/dm/health` instead of `/`
**Fix:** `tests/test_smoke.py` — `test_dm_runtime_health` now validates `/dm/health` endpoint
**Verified:** 16/16 smoke tests pass on VPS

### ISSUE-002: PLAYTEST-ISSUES.md file was missing from repository
**Fixed:** 2026-04-23 — File created and committed to git (commit 9036249)
**Fix:** Added both PLAYTEST-ISSUES.md and PLAYTEST-GUIDE.md to repo

### ISSUE-003: NPC interact targeting broken — target parameter ignored, random NPC selected
**Fixed:** 2026-04-23 — NPC query now filters by `current_location_id` in addition to biome
**Fix:** `app/routers/actions.py` line 1414 — changed query from `WHERE biome = ?` to `WHERE biome = ? AND current_location_id = ?`
**Root Cause:** Biome-only query returned all NPCs sharing the biome regardless of specific location
**Verified:** Interact with "Sister Drenna" at south-road now correctly returns Drenna dialogue

### ISSUE-004: Character current_location_id not updated after move action
**Fixed:** 2026-04-23 — Move handler now uses resolved location ID from `_resolve_move` instead of raw `body.target`
**Fix:** `app/routers/actions.py` line 748 — changed `(body.target, ...)` to `(result['new_location'], ...)`
**Root Cause:** Raw user input (e.g., "south road") was stored instead of canonical location ID ("south-road"), causing downstream lookup failures
**Verified:** Character location persists correctly after move; GET /characters returns updated location_id

### ISSUE-005: Absurd/impossible actions trigger travel instead of refusal
**Fixed:** 2026-04-23 — Added absurd action guardrail in intent router + refusal narration in synthesis
**Fix:** `dm-runtime/app/services/intent_router.py` — `_ABSURD_PATTERNS` regex list + detection block before default return
**Fix:** `dm-runtime/app/services/synthesis.py` — `_build_absurd_refusal()` generates refusal narration
**Verified:** "I swallow the statue whole" returns refusal narration, no location change

---

## Deployment

**Commit:** 9036249 on main branch
**VPS:** Deployed 2026-04-23 ~09:45 SGT — both containers rebuilt and recreated
**Smoke tests:** 16/16 PASS on VPS

## Playtest Session Reports

### 2026-04-23 02:38 UTC — Heartbeat Agent — Scenario A

**Character:** Playtest-A-20260423023553 (ID: `playtest-a-20260423023553-49b486`)
**Smoke Test:** 16/16 PASS  (production endpoints healthy)

**Transcript:**
- `/characters POST` → 201 created, location `None` initially
- `/characters/.../actions` explore 1 → 200; narration: "statue pointing NE, found 1gp"
- `/characters/.../actions` explore 2 → 200; narration: "nothing of value"
- `/dm/turn` examine statue → 200; **NARRATION MISMATCH** (Marta merchant returned)
- `/narrative/flags/{id}` → 200; `thornhold_statue_observed=1`, `seal_awareness=1`
- `/narrative-introspect/character/{id}/summary` → 200; no endings unlocked

**Flags Set:** `thornhold_statue_observed`, `seal_awareness`
**Character State:** location_id=`thornhold`, hp=`12/12`  (persistence CORRECT)

**Issues Found:**
- NEW: ISSUE-006 — DM narration synthesis returns wrong NPC content for statue interaction

**Notes:** Scenario A mechanically complete. Statue flag set correctly. DM narration quality bug confirmed.

### 2026-04-23 03:37 UTC — Heartbeat Agent — Scenario B

**Character:** HB-ScenB-20260423033657 (ID: `hb-scenb-20260423033657-db080c`)
**Smoke Test:** 16/16 PASS

**Evidence:**
- Move to cave-entrance (no statue): 200 with refusal narration "can't reach ... Available paths: forest-edge, south-road"
- Statue flag set after 1 explore: thornhold_statue_observed=1
- DM statue examine: Ser Maren (guard) — correct (ISSUE-006 NOT reproduced)
- Move to south-road: current_location_id = None after move (P1 persistence bug — ISSUE-007)
- Final flags: thornhold_statue_observed=1

**Issues:** ISSUE-006 (no repro) | ISSUE-007 (new P1)

**Final state:** location=None, hp=12/12

---


### 2026-04-23 04:51 UTC — Heartbeat Agent — Scenario C Attempt

**Character:** Playtest-C-20260423044954 (ID: `playtest-c-20260423044954-9f7e04`)
**Smoke Test:** 16/16 PASS

**Transcript:**
- `/characters POST` → 201 created, location=thornhold, HP=12/12
- `explore` x1 → 200; narration: "find 3 gold pieces... also notice the old statue"
- Flags: `thornhold_statue_observed=1` set correctly
- `move target=south-road` → 200 success=True; GET confirms `location_id=south-road` ✓ (ISSUE-007 not reproduced)
- `explore` at south-road → 200; no combat triggered (`combat: null`)
- `dm/turn` "look for danger" → narration "Traveled to The Crossroads", location changed to crossroads
- Attempted `move target=forest-edge` from crossroads → 200 success=False, narration: "can't reach... Available paths: south-road, mountain-pass"
- Verified via independent character: forest-edge reachable from thornhold with statue flag, but script state corruption prevents this path

**Issues Found:**
- ISSUE-006 (statue-examine wrong NPC): not encountered (flow did not reach statue-examine DM turn)
- ISSUE-007 (location persistence after move): NOT reproduced — location persisted correctly in 3 move cycles
- NEW: ISSUE-008 — playtest harness crashes before combat due to invalid location target + missing success validation

**Notes:** Scenario C could not be completed because the playtest harness is broken. The production endpoints correctly support combat chain (forest-edge accessible, move actions work, flags set), but the script's logic errors abort before combat. Specifically: (1) `target="south-rd"` (non-existent) triggers 404, (2) prior state.location_id corruption from ignored `success=false` response damages world routing. Recommended: fix harness then rerun Scenario C with fresh char. Character deleted after test.


### 2026-04-23 05:43 UTC — Heartbeat Agent — Scenario D

**Character:** HB-D-1776922931 (ID: `hb-d-1776922931-8b2d36`)
**Smoke Test:** 16/16 PASS

**Transcript (key steps):**
- Character creation → 201, location=thornhold, HP=12/12
- Explore x1 → 200; set `thornhold_statue_observed=1`
- Move to south-road → 200 success, location_id confirmed via GET
- DM turn "I want to speak with Sister Drenna." → 200; correct Drenna narration delivered
- Backtrack to thornhold → move failed (character already at south-road)
- Move to forest-edge → 200; then deep-forest → 200; both verified
- Explore deep-forest → loot events; unlocked cave-entrance
- Move to cave-entrance → 200; explore unlocked cave-depths
- Move to cave-depths → 200; confirmed at cave-depths
- DM turn "Brother Kol, I want to understand your story." → 200; correct Kol narration (cult-leader)
- Final flags: `thornhold_statue_observed=1`, `kol_brother_met=1`; `kol_backstory_known` NOT set

**Flags Set:** `thornhold_statue_observed`, `kol_brother_met`
**Character State:** Final location=cave-depths, HP=12/12

**Issues Found:**
- CONFIRMED: ISSUE-006 — statue-examination returns wrong NPC (Ser Maren instead of statue), reproduced via isolated test
- NOT REPRODUCED: ISSUE-007 — location persistence verified across 6 moves
- NOT REPRODUCED: ISSUE-008 — harness bug (unrelated to production endpoints)

**Notes:**
- Drenna and Kol interactions produced correct NPC-specific content when properly positioned.
- Combat chain traversal required sequential exploration to unlock next region: forest-edge after initial explore, deep-forest after arrival, cave-entrance after deep-forest explore, cave-depths after cave-entrance explore.
- Quest flag `kol_backstory_known` did not auto-set after Kol dialogue; may require explicit quest acceptance action or additional Drenna confession not triggered.
- World geography to reach Kol works via combat chain path (forest-edge→deep-forest→cave-entrance→cave-depths). Drenna reachable directly via south-road.
### 2026-04-23 06:45 UTC — Heartbeat Agent — Scenario E (Portal / Ending Access)

**Character:** ScenarioE-run (ID: `scenarioe-1776926233-a5caae`)
**Smoke Test:** 16/16 PASS (production endpoints healthy)

**Path taken:**
- Thornhold -> explore (set thornhold_statue_observed=1)
- South-road (move success)
- Back to thornhold (move success)
- Forest-edge (move success; encounter triggered: goblin ambush — resolved via DM turn)
- Deep-forest (move success)
- Cave-entrance (move success)
- Cave-depths (move success; reached Seal Chamber)

**Flags captured:** `thornhold_statue_observed=1`

**Key Evidence:**
- `/characters POST` → 201 created, initial location thornhold
- `/characters/{char_id}/actions` explore → 200, set statue flag
- Move actions: status 200 with success=True, location confirmed via GET
- Final GET `/characters/{char_id}` → `location_id = cave-depths` ✓
- `/portal/token` POST → **500 Internal Server Error**

**Issues Found:**
- CONFIRMED: ISSUE-006 — DM statue-examine returns wrong NPC (Ser Maren guard)
- NOT REPRODUCED: ISSUE-007 — location persistence OK
- NOT REPRODUCED: ISSUE-008 — harness bug bypassed
- **NEW: ISSUE-009** — Portal token generation fails with 500 (P1-High)

**Notes:** World connectivity verified. Endings: Reseal reachable, Merge reachable, Communion NOT reachable (missing `kol_backstory_known`). Portal token endpoint blocks Scenario E.

### 2026-04-23 07:43 UTC — Heartbeat Agent — Scenario A

**Character:** hb-scenA-1776929801-1b2699 (ID: `hb-scena-1776929801-1b2699-473423`)
**Smoke Test:** 16/16 PASS (production endpoints healthy)

**Transcript (key calls):**
- POST `/characters` → 201 created, `location_id='thornhold'` (initial `current_location_id=None`)
- POST `/characters/{id}/actions` explore → 200; narration: "You search Thornhold but find nothing of value. You glance at the statue..."; flag `thornhold_statue_observed=1`
- POST `/dm/turn` with "I examine the statue carefully" → 200; narration **"You approach Marta the Merchant (merchant). Looking to buy or sell?"** — ISSUE-006 reproduced
- POST `/characters/{id}/actions` move to south-road → 200 success; `character_state.location_id='south-road'` (verified via GET: `location_id='south-road'`, `current_location_id=None`) — ISSUE-007 field discrepancy persists

**Flags Set:** `thornhold_statue_observed=1`
**Final Character State:** `location_id` updates correctly (tested: south-road ↔ thornhold), but `current_location_id` remains `None`

**Issues Confirmed:**
- ISSUE-006 (P2) — DM statue-examination returns wrong NPC (Marta). Reproduced.
- ISSUE-007 (P1) — `current_location_id` field never set; discrepancy with `location_id`.
- ISSUE-009 (P1) — Portal token now functional (returns 201); not reproduced.

**Notes:**
- Harness (ISSUE-008) remains broken; Scenario A bypassed via direct API calls.
- Communion ending still unreachable (ISSUE-013 external); not addressed this run.
- Recommend: (1) Fix synthesis routing for statue interaction (ISSUE-006), (2) Align `current_location_id` with `location_id` state updates (ISSUE-007), (3) Verify ISSUE-009 resolution across multiple runs; consider closing.

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
