#!/usr/bin/env python3
"""
D20 Heartbeat — Post-Fix Retest Evidence Update (rev7 — atomic create+evidence)
Creates ISSUE-018–022 with embedded evidence in one pass; prepends session report; validates.
"""

import os, re, datetime, sys

REPO_ROOT = '/home/rigario/Projects/rigario-d20'
ISSUES_PATH = os.path.join(REPO_ROOT, 'PLAYTEST-ISSUES.md')

with open(ISSUES_PATH, 'r') as f:
    content = f.read()

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Post-Fix Retest (P0 blockers live)"

# -------------------------------------------------------------------------
# Build complete issue blocks for P0 blockers (018–022) with evidence embedded
# -------------------------------------------------------------------------

issue_018_full = f"""

### ISSUE-018: DM planner cannot see NPCs present at current location (P0-Critical)

**MC Task:** #529218b9  \\
**Severity:** P0-Critical  \\
**Category:** Narrative / DM context  \\
**Reproduces:** YES — live production

**Heartbeat Check ({ts} — ISSUE-018 NPC context):**
    - Probe char: retest-npc-1777314748-6762e9 at rusty-tankard
    - /npcs/at/rusty-tankard: 200 → [npc-aldric, npc-bohdan, npc-tally]
    - Direct interact target='Aldric the Innkeeper': 200 success, proper dialogue returned
    - DM turn 'I talk to Aldric the Innkeeper.': scene='\"aldric\" isn't here. Available: no one.' | npc_lines=[]
    - intent_used.target='aldric' (raw, not 'npc-aldric'), available_actions=[]
    - Conclusion: DM planner world context excludes location NPCs — false absence confirmed live

"""

issue_019_full = f"""

### ISSUE-019: DM natural target normalization fails for canonical locations/NPCs (P0-Critical)

**MC Task:** #88880a54  \\
**Severity:** P0-Critical  \\
**Category:** Intent routing / affordance planner  \\
**Reproduces:** YES — live production

**Heartbeat Check ({ts} — ISSUE-019 target normalization):**
    - DM turn 'I go to Thornhold town square.' → 'Location not found: thornhold town square' (raw alias forwarded)
    - DM turn 'I talk to Sister Drenna.' → '\"sister\" isn't here.' (not normalized)
    - Direct move target='thornhold': 200 success → location updated
    - Direct interact target='Sister Drenna': 200 success → proper dialogue
    - Aldric by full name 'Speak with Aldric the Innkeeper.' succeeded (edge case exact match)
    - Conclusion: Intent router fails to normalize natural aliases to canonical IDs; regression confirmed live

"""

issue_020_full = f"""

### ISSUE-020: XP/read-model/level-up progression loop is not playthrough-usable (P0-Critical)

**MC Task:** #b40a62d1  \\
**Severity:** P0-Critical  \\
**Category:** Progression / serialization / auth  \\
**Reproduces:** YES — blocked by ISSUE-017

**Heartbeat Check ({ts} — ISSUE-020 XP/level-up — status):**
    - ISSUE-017 world-graph collapse (all exits None) blocks traversal to combat encounters
    - World data: total=10 locations, every exits field = None (zero connectivity)
    - Without reachable combat, cannot verify XP acquisition or level-up availability
    - Status: deferring full retest until ISSUE-017 resolved

"""

issue_021_full = f"""

### ISSUE-021: full_playthrough_with_gates.py cannot recover from failed movement/combat/death state (P1-High)

**MC Task:** #bce39ecd  \\
**Severity:** P1-High  \\
**Category:** Playtest harness  \\
**Reproduces:** YES — live production

**Heartbeat Check ({ts} — ISSUE-021 harness recovery):**
    - Ran scripts/full_playthrough_with_gates.py (CONTINUE=1)
    - Phase 4: combat triggered at forest-edge (wolves); character becomes combat_active
    - Phase 5: MOVE crossroads → 403 combat_active (server correct)
    - Harness behavior: unhandled HTTPStatusError; aborted; did NOT classify state or recover
    - Character final: hp=None/None, location=forest-edge, stuck in active combat
    - Conclusion: Harness lacks robust invalid-state recovery; crashes on combat_active

"""

issue_022_full = f"""

### ISSUE-022: encounter balance / safe validation route needed for short freeze playthrough (P1-High)

**MC Task:** #b353721b  \\
**Severity:** P1-High  \\
**Category:** Gameplay balance / playtest route  \\
**Reproduces:** YES — blocked by ISSUE-017

**Heartbeat Check ({ts} — ISSUE-022 safe route — status):**
    - ISSUE-017 world-graph collapse (exits all None) prevents building safe traversal path
    - Only hardcoded fallback edges available (thornhold↔forest-edge); narrative arc nodes unreachable
    - Safe non-lethal validation route impossible until world topology reseeded
    - Status: deferring until ISSUE-017 resolved

"""

# -------------------------------------------------------------------------
# Insert new issues at end of Open Issues body (before Deployment H2)
# -------------------------------------------------------------------------
new_issues_blocks = [issue_018_full, issue_019_full, issue_020_full, issue_021_full, issue_022_full]

oi = re.search(r'\n## Open Issues\n', content)
after_oi = content[oi.end():]
nxt = re.search(r'\n## [A-Z]', after_oi)  # next H2, usually Deployment
insert_pt = oi.end() + nxt.start()

# Insert all blocks in reverse order so they appear 018,019,020,021,022 top-to-bottom
for block in reversed(new_issues_blocks):
    if content[insert_pt-1:insert_pt] != '\n':
        block = '\n' + block
    content = content[:insert_pt] + block + content[insert_pt:]
    # update insert_pt for next (prepend) — shift forward by length(block)
    insert_pt += len(block)

# -------------------------------------------------------------------------
# Prepend session report to PSR body (newest-first)
# -------------------------------------------------------------------------
psr = re.search(r'\n## Playtest Session Reports\n', content)
if not psr:
    print("ERROR: PSR not found", file=sys.stderr); sys.exit(1)

session_md = f"\n{session_header}\n\n**Pre-Flight:**\n  Smoke 20/20 PASS | /health=200 | /dm_health=200 | /api/map/data=200 (10 locations, exits all None)\n  Cadence: playtest mode, tick_interval=180s — healthy\n\n**P0 Retest Findings:**\n  ISSUE-018 (#529218b9): FAIL — DM planner lacks NPC context (live)\n  ISSUE-019 (#88880a54): FAIL — natural aliases not normalized (live)\n  ISSUE-020 (#b40a62d1): DEFERRED — world-graph collapse (ISSUE-017) blocks traversal\n  ISSUE-021 (#bce39ecd): FAIL — harness abort on combat_active (live)\n  ISSUE-022 (#b353721b): DEFERRED — same topology blocker\n\n**Evidence IDs:**\n  018: retest-npc-1777314748-6762e9; /npcs/at shows Aldric/Bohdan/Tally but DM says 'no one'\n  019: 'Thornhold town square' raw location error; 'Sister Drenna' → '\"sister\" isn\\'t here'\n  021: full_playthrough_with_gates.py → 403 combat_active unhandled; character stuck forest-edge\n  017: 10/10 exits=None — root cause blocking 020/022\n\n**Next:** Redeploy latest main (triad deployment-lag). Post-deploy: rerun smoke, then retest 020/022.\n\n"

content = content[:psr.end()] + session_md + content[psr.end():]

# -------------------------------------------------------------------------
# Last Reviewed update
# -------------------------------------------------------------------------
ctx = "Smoke 20/20 PASS — 018/019/021 FAIL live; 020/022 deferred (ISSUE-017)"
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — {ctx}"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)

# -------------------------------------------------------------------------
# Header reconciliation via Fixed-marker scan
# -------------------------------------------------------------------------
open_c = 0; fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_start = m.end()
    win = content[body_start:body_start+10000]
    nxt_match = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', win)
    body = content[body_start:body_start+(nxt_match.start() if nxt_match else 10000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1

m_h = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', content)
if m_h:
    hdr_open = int(m_h.group(2))
    hdr_fixed = int(m_h.group(3).split()[-1])
    if hdr_open != open_c or hdr_fixed != fixed_c:
        new_hdr = f"{m_h.group(1)}{open_c} | **Fixed Issues:** {fixed_c}"
        content = content.replace(m_h.group(0), new_hdr, 1)
        print(f"Header reconciled: Open={open_c}, Fixed={fixed_c}")

# -------------------------------------------------------------------------
# VALIDATION
# -------------------------------------------------------------------------
errors = []

# Unique timestamp
if content.count(f"### {ts} — Heartbeat Agent") != 1:
    errors.append("Duplicate session timestamp")

# Session in PSR body and first
psr2 = re.search(r'\n## Playtest Session Reports\n', content)
after2 = content[psr2.end():]
nxt2 = re.search(r'\n## [A-Z]', after2)
psr_body2 = after2[:nxt2.start()] if nxt2 else after2
if session_header not in psr_body2:
    errors.append("Session not inside PSR body")
if not psr_body2.lstrip('\n').startswith(session_header):
    errors.append("Session not first heading in PSR body")

# Double separators
if re.search(r'---\n\s*---\n', content):
    errors.append("Double separator found")

# Stray issues in Deployment only (Fixed Issues allowed)
dep = re.search(r'\n## Deployment\n', content)
if dep:
    snippet = content[dep.start():dep.start()+3000]
    stray = re.findall(r'\n### ISSUE-\d+:', snippet)
    if stray:
        errors.append(f"ISSUE headings in Deployment: {stray}")

# Last Reviewed fresh
if not re.search(r'\*\*Last Reviewed:\*\* ' + re.escape(ts), content):
    errors.append("Last Reviewed not updated")

# Header vs body recount
open_r = 0; fixed_r = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_s = m.end()
    win = content[body_s:body_s+10000]
    nxtm = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', win)
    body = content[body_s:body_s+(nxtm.start() if nxtm else 10000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_r += 1
    else:
        open_r += 1
if open_r != open_c or fixed_r != fixed_c:
    errors.append(f"Header/body count mismatch: hdr {open_c}/{fixed_c} vs body {open_r}/{fixed_r}")

if errors:
    print("VALIDATION FAILURES:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)

# Atomic write
tmp = ISSUES_PATH + '.tmp'
with open(tmp, 'w') as f:
    f.write(content)
os.replace(tmp, ISSUES_PATH)

print(f"""D20 PLAYTEST HEARTBEAT — Post-Fix Retest (SUCCESS)
Timestamp: {ts}
Smoke: 20/20 PASS | Infrastructure: healthy
P0 Retest Summary:
  ISSUE-018 (#529218b9) — FAIL (DM planner NPC context missing — live)
  ISSUE-019 (#88880a54) — FAIL (natural alias normalization broken — live)
  ISSUE-020 (#b40a62d1) — DEFERRED (ISSUE-017 world-graph collapse blocks traversal)
  ISSUE-021 (#bce39ecd) — FAIL (harness abort on combat_active, no recovery — live)
  ISSUE-022 (#b353721b) — DEFERRED (same topology blocker)
ISSUE-017 Active: P1-High — all 10 locations exits=None (blocks traversal)
File updated: PLAYTEST-ISSUES.md (Open={open_c}, Fixed={fixed_c})
""")
sys.exit(0)
