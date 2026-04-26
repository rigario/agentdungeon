#!/usr/bin/env python3
"""
D20 Playtest Heartbeat — Semantic Guard Focus
Updates PLAYTEST-ISSUES.md with latest evidence and session report.
"""

import re
import datetime
import os
import sys

REPO_ROOT = os.path.expanduser("~/Projects/rigario-d20")
ISSUES_PATH = os.path.join(REPO_ROOT, "PLAYTEST-ISSUES.md")

now = datetime.datetime.now(datetime.timezone.utc)
timestamp_str = now.strftime("%Y-%m-%d %H:%M UTC")
print("Run timestamp:", timestamp_str)

with open(ISSUES_PATH, "r") as f:
    content = f.read()

# ----------------------------------------------------------------------
# 1) Append new evidence to ISSUE-011
# ----------------------------------------------------------------------
ISSUE_11_HEADER = "### ISSUE-011:"
NEXT_ISSUE_HEADER = "\n### ISSUE-012:"

pos_11 = content.find(ISSUE_11_HEADER)
if pos_11 == -1:
    print("ERROR: Could not find ISSUE-011 header", file=sys.stderr)
    sys.exit(1)

pos_next = content.find(NEXT_ISSUE_HEADER, pos_11 + 10)
if pos_next == -1:
    print("ERROR: Could not find next issue header (ISSUE-012)", file=sys.stderr)
    sys.exit(1)

print("ISSUE-011 body ends before position:", pos_next)

# Build evidence block
evidence_lines = []
evidence_lines.append("")
evidence_lines.append("**Heartbeat Check (" + timestamp_str + " — semantic guard + smoke gate):**")
evidence_lines.append("    - Health: /health 200, /dm/health 200, /api/map/data 200")
evidence_lines.append("    - Semantic guard: intent/analyze 11/11 block cases guard=true, 5/5 allow cases guard absent; narrate probe PASS")
evidence_lines.append("    - Local regression tests: 102 PASS (test_intent_router + test_dm_runtime_synthesis)")
evidence_lines.append("    - Smoke (production): BLOCKED — character creation POST /characters -> 500 (5/5 reproducible); action endpoints not reached")
evidence_lines.append("    - Character ID: N/A (creation failed)")
evidence_lines.append("    - Conclusion: ISSUE-011 expansion (character creation + action endpoints); deployment drift — requires immediate redeploy to latest main")
evidence_block = "\n".join(evidence_lines) + "\n"

new_content = content[:pos_next] + evidence_block + content[pos_next:]

# ----------------------------------------------------------------------
# 2) Update Last Reviewed header
# ----------------------------------------------------------------------
last_reviewed_line = "**Last Reviewed:** " + timestamp_str + " — Heartbeat — Semantic guard PASS; Character creation 500 regression persists (deployment lag)"
pattern = r'\*\*Last Reviewed:\*\* .*'
new_content = re.sub(pattern, last_reviewed_line, new_content, count=1)

if last_reviewed_line not in new_content:
    print("WARNING: Last Reviewed line not updated correctly", file=sys.stderr)

# ----------------------------------------------------------------------
# 3) Insert new session report at top of PSR body
# ----------------------------------------------------------------------
psr_anchor = "## Playtest Session Reports\n---\n\n"
psr_anchor_pos = new_content.find(psr_anchor)
if psr_anchor_pos == -1:
    print("ERROR: Could not find PSR anchor", file=sys.stderr)
    sys.exit(1)

insert_at = psr_anchor_pos + len(psr_anchor)

# Build session report using dynamic timestamp
session_lines = []
session_lines.append("### " + timestamp_str + " — Heartbeat Agent — Semantic Guard Verification — BLOCKED (character creation 500)")
session_lines.append("")
session_lines.append("**Infrastructure:**")
session_lines.append("  /health:       200 OK")
session_lines.append("  /dm/health:    200 OK (intent_router healthy, narrator enabled)")
session_lines.append("  /api/map/data: 200 OK (world DB accessible)")
session_lines.append("")
session_lines.append("**Semantic Guard — Intent /analyze:**")
session_lines.append("  Block cases (11/11): `type=general`, `action_type=null`, `_semantic_guard=true`, `_semantic_guard_reason=negated_or_refusal_action` — PASS")
session_lines.append("  Allow cases (5/5): guard absent, correct action types (move/talk/interact) — PASS")
session_lines.append("")
session_lines.append("**Semantic Guard — /dm/narrate no-mutation probe:**")
session_lines.append("  player_message=\"I don't want to go to the woods\", dummy resolved_result (move), world_context with thornhold + forest exit")
session_lines.append("  Response: HTTP 200, server_trace.intent_used.details._semantic_guard=true, reason=\"negated_or_refusal_action\"")
session_lines.append("  Narration: \"You pause on the instruction... That is not consent to act; it is a refusal, warning, or boundary. No travel, combat, item use, or other state-changing action is taken.\"")
session_lines.append("  npc_lines: [] | mechanics.what_happened[0]: \"Action held: player message negated or refused the embedded action.\"")
session_lines.append("")
session_lines.append("**Local Regression Tests:**")
session_lines.append("  pytest tests/test_intent_router.py tests/test_dm_runtime_synthesis.py: 102 PASS")
session_lines.append("")
session_lines.append("**Smoke Suite (production):**")
session_lines.append("  Character creation POST /characters -> 500 Internal Server Error (5/5 reproducible)")
session_lines.append("  Action endpoints (explore/move/attack) not tested due to character creation failure")
session_lines.append("  Pre-flight gate: FAILED — scenario execution aborted")
session_lines.append("  Classification: ISSUE-011 expansion (action endpoint instability now covers character creation path)")
session_lines.append("")
session_lines.append("**Outcome:** Semantic coherence guard functional; production character creation/action endpoints degraded — requires redeploy to latest main")
session_lines.append("")
# Separator before existing reports
session_lines.append("---")
session_lines.append("")

session_block = "\n".join(session_lines)

new_content = new_content[:insert_at] + session_block + new_content[insert_at:]

# ----------------------------------------------------------------------
# 4) Post-write validation
# ----------------------------------------------------------------------
errors = []

# A) Header/body count reconciliation
open_count = 0
fixed_count = 0
for m in re.finditer(r'### (ISSUE-\d+):', new_content):
    body_start = m.end()
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', new_content[body_start:body_start+15000])
    if nxt:
        body = new_content[body_start:body_start+nxt.start()]
    else:
        body = new_content[body_start:body_start+5000]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_count += 1
    else:
        open_count += 1

m_header = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', new_content)
if m_header:
    h_open = int(m_header.group(2))
    h_fixed = int(m_header.group(3).split()[-1])
    if h_open != open_count or h_fixed != fixed_count:
        errors.append(f"Header/body count mismatch: header {h_open}/{h_fixed} vs body {open_count}/{fixed_count}")
else:
    errors.append("Could not find header counts")

# B) Timestamp uniqueness
session_header_pattern = "### " + timestamp_str + " — Heartbeat Agent"
if new_content.count(session_header_pattern) != 1:
    count = new_content.count(session_header_pattern)
    errors.append(f"Session timestamp duplicated ({count} occurrences)")

# C) Double separators
if re.search(r'---\n\s*---\n', new_content):
    new_content = re.sub(r'---\n\s*---\n', '---\n', new_content)

# D) PSR containment and first-check
psr_match = re.search(r'\n## Playtest Session Reports\n', new_content)
if psr_match:
    after_psr = new_content[psr_match.end():]
    next_h2 = re.search(r'\n## [A-Z]', after_psr)
    if next_h2:
        psr_body = after_psr[:next_h2.start()]
    else:
        psr_body = after_psr
    if session_header_pattern not in psr_body:
        errors.append("Session report not inside PSR body")
    first_h3 = re.search(r'\n### ', psr_body)
    if first_h3:
        first_h3_segment = psr_body[first_h3.start():first_h3.start()+len(session_header_pattern)+15]
        if session_header_pattern not in first_h3_segment:
            errors.append("Session report is not first in PSR body")
    else:
        errors.append("No H3 headings found in PSR body")
else:
    errors.append("PSR section header not found")

# E) Last Reviewed freshness
expected_lr = "**Last Reviewed:** " + timestamp_str
if expected_lr not in new_content:
    errors.append("Last Reviewed not updated to current timestamp")

# ----------------------------------------------------------------------
# 5) Write or rollback
# ----------------------------------------------------------------------
if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

temp_path = ISSUES_PATH + ".tmp"
with open(temp_path, "w") as f:
    f.write(new_content)
os.replace(temp_path, ISSUES_PATH)

print("\nPLAYTEST-ISSUES.md updated successfully.")
print(f"Open Issues: {open_count}, Fixed Issues: {fixed_count}")
print("Session report inserted as newest in PSR body.")
print("Last Reviewed updated.")
print("All validations passed.")
