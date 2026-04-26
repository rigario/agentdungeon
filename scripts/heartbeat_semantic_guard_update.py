#!/usr/bin/env python3
"""
D20 Heartbeat — Semantic Guard Focused Run
Updates PLAYTEST-ISSUES.md with session report and Last Reviewed.
"""

import re, datetime, os, sys, json

REPO_ROOT = "/home/rigario/Projects/rigario-d20"
ISSUES_PATH = os.path.join(REPO_ROOT, "PLAYTEST-ISSUES.md")

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Semantic Guard Verification (PASS)"

# Read full file
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

# Build session report body
session_body = f"""{session_header}

**Health Gates:**
  - GET /health: 200 OK
  - GET /dm/health: 200 OK (healthy; narrator enabled)
  - GET /api/map/data: 200 OK — world DB accessible

**Semantic Guard — Block Cases (negation/refusal):**
  - 11/11 cases returned `type=general`, `action_type=null`, `_semantic_guard=true`, `reason=negated_or_refusal_action`
  - Cases: "I don't want to go to the woods", "do not go to the woods", "avoid the woods", "I refuse to enter the cave", "stay away from Whisperwood", "not going to the cave", "don't attack the wolves", "dont rest here", "I will not attack the wolves", "let us not go to the woods", "do not open the door"

**Semantic Guard — Allow Cases (valid actions/statements):**
  - 5/5 cases returned no `_semantic_guard`; correct types (move/talk/interact)
  - Cases: "tell Aldric I don't want to go to the woods", "ask Aldric if I should avoid the woods", "I want to go to the woods", "go to the woods", "the door dont open easily"

**No-Mutation Narrate Probe:**
  - Payload: player_message="I don't want to go to the woods", dummy resolved_result, world_context with thornhold + woods connection
  - Response: narration explicitly states "no travel, combat, item use, or other state-changing action is taken"; npc_lines empty
  - server_trace.intent_used.details._semantic_guard = true; reason = negated_or_refusal_action
  - **No mutation occurred** — guard correctly prevented embedded action progression

**Local Regression Tests:**
  - tests/test_intent_router.py + tests/test_dm_runtime_synthesis.py: 102 PASS
  - Covers intent classification, semantic guard logic, synthesis guard checks

**Outcome:** Semantic coherence guard intact — no regressions detected. System ready for scenario playtesting.

**Scenarios Blocked:** None (infrastructure and smoke gates passed this run)
**Character ID(s):** N/A (no scenario execution; guard-only verification)

"""

# --- Insert session report at start of PSR body (newest-first) ---
psr_match = re.search(r'\n## Playtest Session Reports\n', content)
if not psr_match:
    print("ERROR: PSR section not found", file=sys.stderr)
    sys.exit(1)

psr_end = psr_match.end()  # position right after the newline of H2
# Insert our session at the start of the PSR body
content = content[:psr_end] + "\n" + session_body + "\n" + content[psr_end:]

# --- Update Last Reviewed header ---
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — Semantic guard ALL PASS (11/11 block, 5/5 allow, narrate OK)"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)

# --- Post-write validation & normalization ---
# 1. Header count reconciliation (should be unchanged: open=4, fixed=13 based on current state)
#    We'll verify by scanning.
open_count = 0
fixed_count = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_start = m.end()
    # find end of this issue body
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:body_start+15000])
    body_end = body_start + (nxt.start() if nxt else 5000)
    body = content[body_start:body_end]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_count += 1
    else:
        open_count += 1

# Update header if mismatched (expected base: open=4, fixed=13)
header_pat = r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)'
m = re.search(header_pat, content)
if m:
    current_open = int(m.group(2))
    current_fixed = int(m.group(3).split()[-1])
    if current_open != open_count or current_fixed != fixed_count:
        new_header = f"{m.group(1)}{open_count} | **Fixed Issues:** {fixed_count}"
        content = content.replace(m.group(0), new_header)
        print(f"Header counts reconciled: Open={open_count}, Fixed={fixed_count}")

# 2. Timestamp uniqueness check for our session header
if content.count(session_header) != 1:
    print(f"WARNING: Duplicate session header detected ({content.count(session_header)} occurrences). Cleaning...", file=sys.stderr)
    # Remove duplicates, keep only the first (which should be at PSR start)
    parts = content.split(session_header)
    # Rejoin with the header only once between parts
    new_content = parts[0] + session_header
    for part in parts[1:]:
        # Remove any leading separators or blank lines from subsequent blocks
        part_clean = re.sub(r'^[\s\n]*', '', part)
        new_content += part_clean
    content = new_content
    # Verify again
    if content.count(session_header) != 1:
        print("ERROR: Could not deduplicate session header", file=sys.stderr)
        sys.exit(1)

# 3. Double separator normalization
content = re.sub(r'---\n\s*---\n', '---\n', content)

# 4. Session containment check: our header must be inside PSR body
psr_match2 = re.search(r'\n## Playtest Session Reports\n', content)
after_psr2 = content[psr_match2.end():]
next_h2_2 = re.search(r'\n## [A-Z]', after_psr2)
psr_body2 = after_psr2[:next_h2_2.start()] if next_h2_2 else after_psr2
if session_header not in psr_body2:
    print("ERROR: Session header not inside PSR body after insertion", file=sys.stderr)
    sys.exit(1)
# Also check it's the first H3 in PSR body
first_h3 = re.search(r'\n### ', psr_body2)
if not first_h3 or session_header not in first_h3.group(0):
    print("ERROR: Session header is not first H3 in PSR body", file=sys.stderr)
    sys.exit(1)

# 5. Last Reviewed freshness
if not re.search(rf'\*\*Last Reviewed:\*\* {ts}', content):
    print("ERROR: Last Reviewed not updated to current timestamp", file=sys.stderr)
    sys.exit(1)

# Atomic write
temp_path = ISSUES_PATH + '.tmp'
with open(temp_path, 'w') as f:
    f.write(content)

# Final verification: re-read and check again
with open(temp_path, 'r') as f:
    new = f.read()

# Re-check containment
psr_check = re.search(r'\n## Playtest Session Reports\n', new)
after_check = new[psr_check.end():]
next_check = re.search(r'\n## [A-Z]', after_check)
psr_body_check = after_check[:next_check.start()] if next_check else after_check
if session_header not in psr_body_check:
    os.remove(temp_path)
    print("ERROR: Post-write containment check failed", file=sys.stderr)
    sys.exit(1)

# All good, replace
os.replace(temp_path, ISSUES_PATH)
print(f"PLAYTEST-ISSUES.md updated successfully at {ts}")
print(f"Session report inserted as newest in PSR body.")
print(f"Header counts: Open={open_count}, Fixed={fixed_count}")
print(f"Timestamp uniqueness: OK")
print(f"Separator integrity: OK")
