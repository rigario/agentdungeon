#!/usr/bin/env python3
"""
D20 Playtest Heartbeat — P0 Retest Update (2026-04-28)

Atomic update of PLAYTEST-ISSUES.md with evidence for ISSUE-018/019/020 and session report.
Strict boundaries; robust validation.
"""

import re, datetime, os, sys

REPO_ROOT = '/home/rigario/Projects/rigario-d20'
ISSUES_PATH = os.path.join(REPO_ROOT, 'PLAYTEST-ISSUES.md')

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header_line = f"### {ts} — Heartbeat Agent — P0 Retest (018/019/020) — BLOCKED"

# Evidence blocks (no f-strings with braces)
evidence_018 = (
    "**Heartbeat Check (2026-04-28 01:35 UTC — ISSUE-018 P0 Retest):**\n"
    "    - Character: p018retest-120c5a at rusty-tankard\n"
    "    - /npcs/at/rusty-tankard: 200 → ['Aldric the Innkeeper', 'Bohdan Ironvein', 'Tally']\n"
    "    - Direct interact target='Aldric the Innkeeper': 200 success, narration proper\n"
    "    - DM turn 'Talk to Aldric the Innkeeper.': ReadTimeout after 30s (HTTP 000, 0 bytes)\n"
    "    - DM turn 'look around': ReadTimeout after 10s (HTTP 000)\n"
    "    - Conclusion: DM runtime unresponsive; NPC context still missing; issue persists with timeout\n"
    "\n"
)

evidence_019 = (
    "**Heartbeat Check (2026-04-28 01:36 UTC — ISSUE-019 P0 Retest):**\n"
    "    - Character: p018retest-120c5a at rusty-tankard\n"
    "    - DM turn 'I go to Thornhold town square.': ReadTimeout after 12s (no JSON, HTTP 000)\n"
    "    - Unable to verify target normalization due to DM unavailability\n"
    "    - Conclusion: Regression likely persists; DM runtime not responding to probe\n"
    "\n"
)

evidence_020 = (
    "**Heartbeat Check (2026-04-28 01:37 UTC — ISSUE-020 XP/level-up structural):**\n"
    "    - Character: p018retest-120c5a\n"
    "    - GET /characters response fields: xp/level/treasure/hp present (structural fix likely deployed)\n"
    "    - End-to-end combat/XP/level-up path: blocked by ISSUE-017 (world exits=None) AND DM turn timeout\n"
    "    - Unable to complete combat victory probe; progression loop remains unverified in playthrough\n"
    "    - Recommendation: Redeploy + topology fix first, then rerun P0 suite\n"
    "\n"
)

# Session block — trailing blank line to separate from next session
session_block = (
    "### 2026-04-28 01:40 UTC — Heartbeat Agent — P0 Retest (018/019/020) — BLOCKED\n"
    "\n"
    "**Pre-Flight:**\n"
    "  /health:        200 OK\n"
    "  /dm/health:     200 OK\n"
    "  /api/map/data:  200 OK (10 locations, all exits=None — ISSUE-017 persists)\n"
    "  Smoke:          20 PASS, 0 FAIL\n"
    "  Cadence:        /cadence/status 200, mode=normal, tick_interval=180s; toggle→playtest OK; tick advanced; config restored\n"
    "\n"
    "**P0 Retest Findings:**\n"
    "  ISSUE-018 (#529218b9): FAIL — DM turn non-responsive (ReadTimeout); direct interact works but DM planner fails\n"
    "  ISSUE-019 (#88880a54): FAIL — DM turn timeout prevents alias normalization check; regression likely persists\n"
    "  ISSUE-020 (#b40a62d1): STRUCTURAL FIX LIKELY PRESENT — GET progression fields present; end-to-end blocked by ISSUE-017 + DM unavailability\n"
    "  ISSUE-021 (#bce39ecd): DEFERRED — P0 failures block harness run\n"
    "  ISSUE-022 (#b353721b): DEFERRED — same\n"
    "\n"
    "**Evidence IDs:**\n"
    "  018: char p018retest-120c5a; /npcs/at lists Aldric/Bohdan/Tally; direct interact works; DM turn times out (30s, HTTP 000)\n"
    "  019: same char; DM turn 'Thornhold town square' times out; no response received\n"
    "  020: char GET shows xp/level/hp/treasure fields; combat/level-up auth path unverified\n"
    "\n"
    "**Next:** Redeploy latest main (triad 017/018/019). DM runtime unresponsiveness suggests deployment drift or resource exhaustion. After redeploy, rerun P0 suite before proceeding to harness/safe-route.\n"
    "\n"
)

# -------------------------------------------------------------------------
# Load
# -------------------------------------------------------------------------
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

# -------------------------------------------------------------------------
# Inject ISSUE-018 evidence (before ## Deployment)
# -------------------------------------------------------------------------
deploy_match = re.search(r'\n## Deployment\n', content)
if not deploy_match:
    print("ERROR: ## Deployment section not found", file=sys.stderr); sys.exit(1)
deploy_pos = deploy_match.start()

if re.search(r'### 2026-04-28 01:35 UTC — Heartbeat Agent', content):
    print("Note: ISSUE-018 evidence already present; skipping duplicate")
else:
    content = content[:deploy_pos] + evidence_018 + content[deploy_pos:]

# -------------------------------------------------------------------------
# Inject ISSUE-019 evidence (before ### ISSUE-018)
# -------------------------------------------------------------------------
issue_018_match = re.search(r'### ISSUE-018:', content)
if not issue_018_match:
    print("ERROR: ISSUE-018 header not found", file=sys.stderr); sys.exit(1)
insert_019_pos = issue_018_match.start()

if re.search(r'### 2026-04-28 01:36 UTC — Heartbeat Agent', content):
    print("Note: ISSUE-019 evidence already present; skipping duplicate")
else:
    content = content[:insert_019_pos] + evidence_019 + content[insert_019_pos:]

# -------------------------------------------------------------------------
# Inject ISSUE-020 evidence (before ### ISSUE-019)
# -------------------------------------------------------------------------
issue_019_match = re.search(r'### ISSUE-019:', content)
if not issue_019_match:
    print("ERROR: ISSUE-019 header not found after injection", file=sys.stderr); sys.exit(1)
insert_020_pos = issue_019_match.start()

if re.search(r'### 2026-04-28 01:37 UTC — Heartbeat Agent', content):
    print("Note: ISSUE-020 evidence already present; skipping duplicate")
else:
    content = content[:insert_020_pos] + evidence_020 + content[insert_020_pos:]

# -------------------------------------------------------------------------
# Insert session at START of PSR body (after PSR header)
# -------------------------------------------------------------------------
psr_match = re.search(r'\n## Playtest Session Reports\n', content)
if not psr_match:
    print("ERROR: PSR section not found", file=sys.stderr); sys.exit(1)
psr_insert = psr_match.end()

# Deduplicate any previous run session with same timestamp pattern
pattern = re.escape(session_header_line)
while True:
    existing = re.search(pattern, content)
    if not existing:
        break
    # Remove from header to next separator or H2/H3
    after = existing.end()
    end_mark = re.search(r'\n---\n|\n### |\n## [A-Z]', content[after:])
    if end_mark:
        content = content[:existing.start()] + content[after + end_mark.start():]
    else:
        content = content[:existing.start()]
    print("Removed duplicate session block")

# Insert: PSR header already followed by newline; we insert our block directly.
# Ensure trailing blank line after session content to separate from next session.
content = content[:psr_insert] + session_header_line + "\n\n" + session_block + content[psr_insert:]

# -------------------------------------------------------------------------
# Update Last Reviewed
# -------------------------------------------------------------------------
last_reviewed_context = "P0 retest 018/019/020 — 018 FAIL (DM timeout), 019 FAIL (timeout), 020 STRUCTURAL OK but blocked"
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — {last_reviewed_context}"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)

# -------------------------------------------------------------------------
# Header count reconciliation via Fixed-marker scan
# -------------------------------------------------------------------------
open_c = 0; fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_start = m.end()
    win = content[body_start:body_start+5000]
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', win)
    body_end = body_start + (nxt.start() if nxt else 5000)
    body = content[body_start:body_end]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1

head_m = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', content)
if head_m:
    new_head = f"**Open Issues:** {open_c} | **Fixed Issues:** {fixed_c}"
    content = content[:head_m.start()] + new_head + content[head_m.end():]
else:
    print("WARNING: Header line not found; counts not updated", file=sys.stderr)

# -------------------------------------------------------------------------
# Normalize double separators
# -------------------------------------------------------------------------
content = re.sub(r'---\n\s*---\n', '---\n', content)

# -------------------------------------------------------------------------
# Atomic write
# -------------------------------------------------------------------------
tmp = ISSUES_PATH + '.tmp'
with open(tmp, 'w') as f:
    f.write(content)

# -------------------------------------------------------------------------
# Post-write validation
# -------------------------------------------------------------------------
with open(tmp, 'r') as f:
    new = f.read()

errs = []

# Header/body count
hm2 = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', new)
if hm2:
    ho = int(hm2.group(2)); hf = int(hm2.group(3).split()[-1])
    if ho != open_c or hf != fixed_c:
        errs.append(f"Header/body count mismatch: header {ho}/{hf} vs body {open_c}/{fixed_c}")
else:
    errs.append("Header line missing after update")

# Timestamp uniqueness
if new.count(session_header_line) != 1:
    errs.append(f"Session header appears {new.count(session_header_line)} times (expected 1)")

# Double separators
if re.search(r'---\n\s*---\n', new):
    errs.append("Double separator sequences present")

# Session inside PSR body
psr_match2 = re.search(r'\n## Playtest Session Reports\n', new)
if psr_match2:
    after_psr2 = new[psr_match2.end():]
    next_h2_2 = re.search(r'\n## [A-Z]', after_psr2)
    psr_body_2 = after_psr2[:next_h2_2.start()] if next_h2_2 else after_psr2
    if session_header_line not in psr_body_2:
        errs.append("Session report NOT inside PSR body")
    # First entry check: strip leading whitespace and ensure it starts with session header
    stripped = psr_body_2.lstrip()
    if not stripped.startswith(session_header_line):
        errs.append("Session report is not the first entry in PSR body (newest-first order violation)")
else:
    errs.append("Playtest Session Reports section missing")

# Last Reviewed freshness
if not re.search(rf'\*\*Last Reviewed:\*\* {ts} — Heartbeat', new):
    errs.append("Last Reviewed not updated with current timestamp")

# Evidence presence
if 'DM turn non-responsive' not in new:
    errs.append("ISSUE-018 evidence block missing")
if 'DM turn timeout' not in new:
    errs.append("ISSUE-019 evidence block missing")
if 'STRUCTURAL FIX LIKELY PRESENT' not in new:
    errs.append("ISSUE-020 evidence block missing")

# -------------------------------------------------------------------------
# Commit or rollback
# -------------------------------------------------------------------------
if errs:
    print("VALIDATION ERRORS:")
    for e in errs:
        print(f"  - {e}")
    os.remove(tmp)
    sys.exit(1)
else:
    os.replace(tmp, ISSUES_PATH)
    print(f"PLAYTEST-ISSUES.md updated successfully at {ts}")
    print(f"Open issues: {open_c}, Fixed: {fixed_c}")
    print("\n--- HEARTBEAT FINAL REPORT ---")
    print(f"Timestamp: {ts}")
    print(f"Probe Character: p018retest-120c5a (location: rusty-tankard)")
    print(f"Smoke Suite: 20/20 PASS")
    print(f"Cadence: OK (tick advanced, config restored)")
    print(f"ISSUE-018 (#529218b9): FAIL — DM turn ReadTimeout; direct interact OK; DM planner lacks NPC context")
    print(f"ISSUE-019 (#88880a54): FAIL — DM turn timeout prevents alias normalization check")
    print(f"ISSUE-020 (#b40a62d1): STRUCTURAL FIX LIKELY PRESENT (GET fields present) but end-to-end progression blocked by ISSUE-017 + DM unavailability")
    print(f"ISSUE-021 (#bce39ecd): DEFERRED")
    print(f"ISSUE-022 (#b353721b): DEFERRED")
    print(f"\nNEXT ACTION: Redeploy latest main (triad 017/018/019). DM runtime unresponsiveness suggests deployment drift or resource exhaustion. After redeploy, rerun P0 suite before proceeding to harness/safe-route.")
    sys.exit(0)
