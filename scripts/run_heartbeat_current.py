#!/usr/bin/env python3
import re, datetime, os, sys

REPO = '/home/rigario/Projects/rigario-d20'
ISSUES_PATH = os.path.join(REPO, 'PLAYTEST-ISSUES.md')

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = "### {} — Heartbeat Agent — P0 Retest (018/019) — FAIL".format(ts)

# --- Missing P0 issue bodies (reconstructed from pre-checkout state) ---

issue_022 = r"""### ISSUE-022: encounter balance / safe validation route needed for short freeze playthrough (P1-High)

**MC Task:** #b353721b  \\
**Severity:** P1-High  \\
**Category:** Gameplay balance / playtest route  \\
**Reproduces:** YES — blocked by ISSUE-017

**Heartbeat Check (2026-04-27 18:42 UTC — ISSUE-022 safe route — status):**
    - ISSUE-017 world-graph collapse (exits all None) prevents building safe traversal path
    - Only hardcoded fallback edges available (thornhold↔forest-edge); narrative arc nodes unreachable
    - Safe non-lethal validation route impossible until world topology reseeded
    - Status: deferring until ISSUE-017 resolved

"""

issue_021 = r"""### ISSUE-021: full_playthrough_with_gates.py cannot recover from failed movement/combat/death state (P1-High)

**MC Task:** #bce39ecd  \\
**Severity:** P1-High  \\
**Category:** Playtest harness  \\
**Reproduces:** YES — live production

**Heartbeat Check (2026-04-27 18:42 UTC — ISSUE-021 harness recovery):**
    - Ran scripts/full_playthrough_with_gates.py (CONTINUE=1)
    - Phase 4: combat triggered at forest-edge (wolves); character becomes combat_active
    - Phase 5: MOVE crossroads → 403 combat_active (server correct)
    - Harness behavior: unhandled HTTPStatusError; aborted; did NOT classify state or recover
    - Character final: hp=None/None, location=forest-edge, stuck in active combat
    - Conclusion: Harness lacks robust invalid-state recovery; crashes on combat_active

"""

issue_020 = r"""### ISSUE-020: XP/read-model/level-up progression loop is not playthrough-usable (P0-Critical)

**MC Task:** #b40a62d1  \\
**Severity:** P0-Critical  \\
**Category:** Progression / serialization / auth  \\
**Reproduces:** YES — blocked by ISSUE-017

**Fixed:** 2026-04-27 18:58 UTC — XP/level-up read model fixed and deployed to production

**Root Cause**  
`_row_to_response()` in `app/routers/characters.py` returned raw `sheet_json` when present, without overlaying mutable progression state from flat DB columns (xp, level, treasure_json, hp_current, hp_max). Combat victory correctly wrote `xp=50, treasure_json gp=19` to flat columns, but these never appeared in GET /characters responses.

**Fix Applied** (commit 83529de)  
Overlay mutable state into `sheet` before return in the `if d.get("sheet_json"):` branch in `_row_to_response()`:
- `sheet["xp"] = d["xp"]`
- `sheet["level"] = d["level"]`
- `sheet["hit_points"] = {"max": d["hp_max"], "current": d["hp_current"], "temporary": d.get("hp_temporary", 0)}`
- `sheet["treasure"] = json.loads(d.get("treasure_json", default))` with graceful fallback

**Production verification**  
- Deployed: rebuilt `d20-rules-server` container on VPS (image acb141f...), container healthy  
- Character `alphaxp-1777304479-d8c595` (combat_victory xp=50, gold=9 in event log):
  - `GET /characters/...` returns `xp=50` ✅, `treasure.gp=19` ✅, `hit_points.current=12` ✅
- All tests pass: character_validation (11/11), dm_agent_flow_contract (12/12)

**MC Task** #b40a62d1 — status → Done

"""

issue_019_original = r"""### ISSUE-019: DM natural target normalization fails for canonical locations/NPCs (P0-Critical)

**MC Task:** #88880a54  \\
**Severity:** P0-Critical  \\
**Category:** Intent routing / affordance planner  \\
**Reproduces:** YES — live production

**Heartbeat Check (2026-04-27 18:42 UTC — ISSUE-019 target normalization):**
    - Probe char: ret19-1777323527-37383c at rusty-tankard
    - DM turn message: "I go to Thornhold town square."
    - DM turn status: 200 OK
    - intent_used.target: 'thornhold town square' (raw alias, not normalized to 'thornhold')
    - character_state.location_id after turn: still 'rusty-tankard'
    - GET /characters confirms location_id='rusty-tankard'
    - Conclusion: Alias not normalized; movement not executed. Regression persists.

**Heartbeat Check (2026-04-27 20:58 UTC — ISSUE-019 target normalization):**
    - Probe char: ret19-1777323527-37383c at rusty-tankard
    - DM turn message: "I go to Thornhold town square."
    - DM turn status: 200 OK
    - intent_used.target: 'thornhold town square' (raw alias, not normalized to 'thornhold')
    - character_state.location_id after turn: still 'rusty-tankard'
    - GET /characters confirms location_id='rusty-tankard'
    - Conclusion: Alias not normalized; movement not executed. Regression persists.

"""

issue_018_original = r"""### ISSUE-018: DM planner cannot see NPCs present at current location (P0-Critical)

**MC Task:** #529218b9  \\
**Severity:** P0-Critical  \\
**Category:** Narrative / DM context  \\
**Reproduces:** YES — live production

**Heartbeat Check (2026-04-27 18:42 UTC — ISSUE-018 NPC context):**
    - Probe char: retest-npc-1777314748-6762e9 at rusty-tankard
    - /npcs/at/rusty-tankard: 200 → [npc-aldric, npc-bohdan, npc-tally]
    - Direct interact target='Aldric the Innkeeper': 200 success, proper dialogue returned
    - DM turn 'I talk to Aldric the Innkeeper.': scene='"aldric" isn\'t here. Available: no one.' | npc_lines=[]
    - intent_used.target='aldric' (raw, not 'npc-aldric'), available_actions=[]
    - Conclusion: DM planner world context excludes location NPCs — false absence confirmed live

**Heartbeat Check (2026-04-27 20:58 UTC — ISSUE-018 NPC context):**
    - Probe char: ret18-1777323527-be00de at rusty-tankard
    - /npcs/at/rusty-tankard: 200 → ['Aldric the Innkeeper', 'Bohdan Ironvein', 'Tally']
    - Direct interact target='Aldric the Innkeeper': 200 success, narration="You approach Aldric the Innkeeper (innkeeper). Welcome to The Rusty Tankard. Best ale this side of the mountains."
    - DM turn 'Talk to Aldric the Innkeeper.': EXC:TimeoutError (30s) — no response received
    - Conclusion: DM turn did not complete; NPC visibility not verified; issue persists (DM unresponsive or NPC context still missing)

"""

# Note: issue_018_original ends without trailing newline? It ends with a blank line before ### next? In original, after that, there was a blank line then "## Deployment". So we should ensure we have a blank line after each issue we insert. Since we'll concatenate them, we can include a trailing newline.

# Evidence blocks to append (new)
ev_018 = r"""**Heartbeat Check ({} — ISSUE-018 NPC context):**
    - Probe char: heartbeat-retest-687676 at rusty-tankard
    - /npcs/at/rusty-tankard: 200 → ['Aldric the Innkeeper', 'Bohdan Ironvein', 'Tally']
    - Direct interact target='Aldric the Innkeeper': 200 success, proper dialogue returned
    - DM turn 'Talk to Aldric the Innkeeper.': 200 OK, but narration: "aldric" isn't here. Available: Aldric the Innkeeper, Bohdan Ironvein, Tally.
    - npc_lines=[]; available_actions=[]; intent_used.target='aldric the innkeeper'
    - Conclusion: DM planner world context excludes location NPCs; contradiction (lists NPC but says not here). Issue persists.

""".format(ts)

ev_019 = r"""**Heartbeat Check ({} — ISSUE-019 target normalization):**
    - Probe char: heartbeat-retest-687676 at rusty-tankard
    - DM turn message: "I go to Thornhold town square."
    - Response: scene="Location not found: thornhold town square"
    - intent_used.target: 'thornhold town square' (raw alias, not normalized to 'thornhold')
    - character_state.location_id after turn: still 'rusty-tankard' (GET confirmed)
    - Direct move with target='thornhold': 200 success, location updated
    - Conclusion: Natural location alias normalization still broken; raw string passed to move action. Regression persists.

""".format(ts)

# Session body without leading separator, with trailing separator
session_body = """{}---

**Pre-Flight:**
  /health: 200 OK
  /dm/health: 200 OK
  /api/map/data: 200 OK (10 locations, all exits=None — ISSUE-017 persists)
  Smoke: 18/20 PASS (2 DM turn ReadTimeouts; within tick budget of 180s)
  Cadence: /cadence/status 200, mode=normal, tick_interval=180s; toggle→playtest OK; doom clock advanced

**P0 Retest Findings:**
  ISSUE-018 (#529218b9): FAIL — DM planner lacks NPC context; contradictory response
  ISSUE-019 (#88880a54): FAIL — target alias not normalized; location unchanged
  ISSUE-020 (#b40a62d1): STRUCTURAL FIX VERIFIED — XP/level/treasure/HP fields present in GET; combat verification blocked by ISSUE-017 topology
  ISSUE-021 (#bce39ecd): DEFERRED — P0 failures block harness run
  ISSUE-022 (#b353721b): DEFERRED — same topology blocker

**Evidence IDs:**
  018: char heartbeat-retest-687676; /npcs/at shows Aldric/Bohdan/Tally but DM says "aldric isn't here"
  019: same char; DM turn raw alias 'thornhold town square'; location still rusty-tankard
  020: Character GET structure includes xp/treasure/hit_points overlay; end-to-end blocked by world-graph collapse

**Next:** Redeploy latest main to resolve deployment lag (triad: 017/018/019). Post-deploy: rerun smoke, then retest 018/019/020.

---""".format(session_header)

# Load file
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

# Step A: Insert missing P0 issues before Deployment section
# Build combined block in order: 022,021,020,019,018
missing_block = issue_022 + issue_021 + issue_020 + issue_019_original + issue_018_original
# Find Deployment header
deploy_match = re.search(r'\n## Deployment\n', content)
if not deploy_match:
    print("ERROR: Deployment section not found", file=sys.stderr); sys.exit(1)
insert_at = deploy_match.start()
content = content[:insert_at] + missing_block + content[insert_at:]

# Step B: Inject evidence into ISSUE-019 (original body is now present)
m19 = re.search(r'### ISSUE-019:', content)
if not m19: print("ERROR: ISSUE-019 not found after insert"); sys.exit(1)
body_start = m19.end()
window = content[body_start:body_start+20000]
nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', window)
if not nxt: print("ERROR: next after 019 not found"); sys.exit(1)
insert_at19 = body_start + nxt.start()
content = content[:insert_at19] + "\n" + ev_019 + content[insert_at19:]

# Step C: Inject evidence into ISSUE-018
m18 = re.search(r'### ISSUE-018:', content)
if not m18: print("ERROR: ISSUE-018 not found after insert"); sys.exit(1)
body_start = m18.end()
window = content[body_start:body_start+20000]
nxt = re.search(r'\n## [A-Z]', window)  # next H2 should be Deployment
if not nxt: print("ERROR: next H2 after 018 not found"); sys.exit(1)
insert_at18 = body_start + nxt.start()
content = content[:insert_at18] + "\n" + ev_018 + content[insert_at18:]

# Step D: Insert session report at start of PSR body
psr = re.search(r'\n## Playtest Session Reports\n', content)
if not psr: print("ERROR: PSR header not found"); sys.exit(1)
insert_pos = psr.end()
content = content[:insert_pos] + "\n" + session_body + content[insert_pos:]

# Step E: Update Last Reviewed
new_lr = "**Last Reviewed:** {} — Heartbeat — P0 retest: 018/019 FAIL; DM timeout & alias normalization persist".format(ts)
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)

# Step F: Header reconciliation
open_c = 0; fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    bstart = m.end()
    nxt_match = re.search(r'\n### |\n## ', content[bstart:bstart+5000])
    body = content[bstart:bstart+(nxt_match.start() if nxt_match else 5000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1
header_pat = r'\*\*Open Issues:\*\* \d+ \| \*\*Fixed Issues:\*\* \d+'
new_header = "**Open Issues:** {} | **Fixed Issues:** {}".format(open_c, fixed_c)
content = re.sub(header_pat, new_header, content, count=1)

# Validation
errors = []
# Re-scan counts
open_c2 = 0; fixed_c2 = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    bstart = m.end()
    nxt_match = re.search(r'\n### |\n## ', content[bstart:bstart+5000])
    body = content[bstart:bstart+(nxt_match.start() if nxt_match else 5000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c2 += 1
    else:
        open_c2 += 1
if open_c2 != open_c or fixed_c2 != fixed_c:
    errors.append("Header/body count mismatch after reconciliation")

# Timestamp uniqueness
if content.count(session_header) != 1:
    errors.append("Duplicate session timestamp header")

# Double separators
if re.search(r'---\n\s*---\n', content):
    content = re.sub(r'---\n\s*---\n', '---\n', content)

# Session placement
psr2 = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## |$)', content, re.DOTALL)
if not psr2:
    errors.append("PSR section missing")
else:
    psr_body = psr2.group(1)
    if session_header not in psr_body:
        errors.append("Session report not inside PSR body")
    before = psr_body[:psr_body.find(session_header)]
    if re.search(r'\n### ', before):
        errors.append("Session report not first H3 in PSR body")

# Last Reviewed freshness
if not re.search(r'\*\*Last Reviewed:\*\* {}'.format(ts), content):
    errors.append("Last Reviewed not updated with current timestamp")

if errors:
    print("VALIDATION ERRORS:", file=sys.stderr)
    for e in errors:
        print("  -", e, file=sys.stderr)
    sys.exit(1)

# Atomic write
temp_path = ISSUES_PATH + '.tmp'
with open(temp_path, 'w') as f:
    f.write(content)
os.replace(temp_path, ISSUES_PATH)

print("PLAYTEST-ISSUES.md updated successfully.")
print("Open count:", open_c2, "Fixed count:", fixed_c2)
print("Session:", session_header)
