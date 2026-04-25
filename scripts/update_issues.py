
import datetime, os, re, subprocess, json

os.chdir('/home/rigario/Projects/rigario-d20')

# Read file
with open('PLAYTEST-ISSUES.md', 'r') as f:
    content = f.read()

now = datetime.datetime.now(datetime.timezone.utc)
timestamp = now.strftime('%Y-%m-%d %H:%M UTC')
run_id = f"heartbeat-b-{now.strftime('%Y%m%dT%H%M%S')}"
char_id = "hbb-202604251545-2bfa3d"

# --- Evidence blocks (no f-string braces issues) ---
evidence_007 = (
    "**Heartbeat Check ({ts} — Scenario B — move persistence):**\n"
    "    - Character: {cid}\n"
    "    - Move action: POST /characters/{{id}}/actions {{\"action_type\":\"move\",\"target\":\"thornhold\"}} → 200, success=True\n"
    "    - GET /characters/{{id}} after move: location_id=\"thornhold\" ✅ but current_location_id=None ❌\n"
    "    - Conclusion: current_location_id regression still live — deployment lag persists\n"
).format(ts=timestamp, cid=char_id)

evidence_017 = (
    "**Heartbeat Check ({ts} — Scenario B — world topology):**\n"
    "    - GET /api/map/data: total=12 locations present\n"
    "    - Every location's `exits` field = None (12/12)\n"
    "    - Explore at thornhold: available_paths = [] (zero connectivity)\n"
    "    - Movement via move action still works (uses fallback), but narrative exploration broken\n"
    "    - Conclusion: World graph exits regression still active — DB seed needs full adjacency reseed\n"
).format(ts=timestamp)

evidence_016 = (
    "**Heartbeat Check ({ts} — supplemental statue probe):**\n"
    "    - Character: {cid} at thornhold; explore did not set statue flag (likely due to zero paths from exits=None)\n"
    "    - DM turn with \"examine statue carefully\": intent_type=\"interact\", target=\"statue carefully\" (correct)\n"
    "    - Narration described stone hand (correct NPC/object), no teleportation\n"
    "    - Conclusion: Intent routing for in-location interaction now works — ISSUE-016 fix appears deployed\n"
).format(ts=timestamp, cid=char_id)

# --- Inject evidence into issues ---
issues_evidence = {
    '007': evidence_007,
    '017': evidence_017,
    '016': evidence_016,
}

for issue_num, ev in issues_evidence.items():
    heading = f'### ISSUE-{issue_num}:'
    pos = content.find(heading)
    if pos == -1:
        print(f"[WARN] Issue {issue_num} not found")
        continue
    # Find end of this issue block: next '### ISSUE-' or '---\n\n' followed by a H2
    search_start = pos + len(heading)
    # Look ahead up to 20000 chars
    window = content[search_start:search_start+20000]
    # Find first occurrence of either '\n### ISSUE-' or '\n---\n\n'
    next_issue = re.search(r'\n### ISSUE-', window)
    next_sep = re.search(r'\n---\n\n', window)
    boundaries = []
    if next_issue:
        boundaries.append(('next_issue', search_start + next_issue.start()))
    if next_sep:
        boundaries.append(('sep', search_start + next_sep.start()))
    if not boundaries:
        insert_at = len(content)
    else:
        # Choose earliest boundary
        boundaries.sort(key=lambda x: x[1])
        insert_at = boundaries[0][1]
    # Insert evidence before that boundary
    content = content[:insert_at] + "\n" + ev + "\n" + content[insert_at:]
    print(f"[INFO] Appended evidence to ISSUE-{issue_num} at {insert_at}")

# --- Build session report ---
session_report = (
    "### {ts} — Heartbeat Agent — Scenario B (Absurd Test) + ISSUE-016 supplemental probe\n"
    "\n"
    "**Character:** {cid}\n"
    "**Smoke Pre-flight:** 19/20 PASS (single failure: test_move_updates_location_id — ISSUE-007)\n"
    "\n"
    "**Scenario B Transcript:**\n"
    "- Move to thornhold: 200 success; location_id=thornhold confirmed, current_location_id=None (ISSUE-007 reproduced)\n"
    "- DM turn \"I swallow the statue\": intent=general, refusal narration provided (\"not possible\"), choices include travel alternatives but no auto-travel occurred; location unchanged\n"
    "- DM turn \"I fly to the moon\": intent=general, refusal narration, no movement\n"
    "- World probe: /api/map/data total=12, exits=None for all 12 locations (ISSUE-017 confirmed)\n"
    "- Explore at thornhold: available_paths=0 (ISSUE-017 symptom)\n"
    "\n"
    "**Supplemental — Statue Interaction (ISSUE-016):**\n"
    "- Explore at thornhold: did not set thornhold_statue_observed (explore paths blocked by exits=None)\n"
    "- DM turn \"examine statue carefully\": intent_type=interact, target=\"statue carefully\" (correct), scene described stone hand, no teleport\n"
    "- Conclusion: Intent routing for valid in-location interaction now correct — ISSUE-016 fix appears deployed\n"
    "\n"
    "**Issues Confirmed:**\n"
    "- ISSUE-007 (P1-High): current_location_id still None after move (deployment lag)\n"
    "- ISSUE-017 (P1-High): all exits None, explore returns no paths (P1-High)\n"
    "- ISSUE-016 (P1-High): statue intent routing now correct — fix likely live\n"
    "\n"
    "**Issues Not Reproduced:**\n"
    "- ISSUE-005 (absurd refusal): DM refused both absurd actions correctly, no misrouting to travel\n"
    "- ISSUE-010 (infrastructure): endpoints healthy, smoke passed\n"
    "\n"
    "**Next Priority:** Redeploy latest main to resolve deployment lag on ISSUE-007 and ISSUE-017\n"
).format(ts=timestamp, cid=char_id)

# --- Insert session report before Template heading ---
anchor = '## Template for New Issues'
pos = content.find(anchor)
if pos == -1:
    raise RuntimeError("Template section not found")

# Before insertion, let's also consume any preceding blank lines to avoid excessive newlines.
# Look backwards from anchor to find the preceding non-newline/non-dash content boundary.
# We'll just insert at anchor position and add our leading separator.
insertion_block = "---\n\n" + session_report + "---\n\n" + anchor
content = content[:pos] + insertion_block + content[pos+len(anchor):]
print(f"[INFO] Inserted session report before Template heading at position {pos}")

# --- Update Last Reviewed ---
new_lr = f"**Last Reviewed:** {timestamp} — Heartbeat — Scenario B + supplement — Issues 007/017 live; 016 resolved; redeploy recommended"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)
print("[INFO] Updated Last Reviewed header")

# --- Post-write validation & atomic write ---
temp_path = 'PLAYTEST-ISSUES.md.tmp'
with open(temp_path, 'w') as f:
    f.write(content)

with open(temp_path, 'r') as f:
    new_content = f.read()

errors = []

# A) Header/body count reconciliation
open_match = re.search(r'## Open Issues\n', new_content)
if not open_match:
    errors.append("Open Issues section missing")
else:
    after_open = new_content[open_match.end():]
    next_h2 = re.search(r'\n## [A-Z]', after_open)
    open_body = after_open[:next_h2.start()] if next_h2 else after_open[:10000]
    body_open = []; body_fixed = []
    for m in re.finditer(r'### (ISSUE-\d+):', open_body):
        body_start = m.end()
        nxt = re.search(r'\n### |\n## ', open_body[body_start:])
        body_end = body_start + (nxt.start() if nxt else 5000)
        block = open_body[body_start:body_end]
        num = m.group(1)
        if re.search(r'\*\*Fixed:\*\*', block):
            body_fixed.append(num)
        else:
            body_open.append(num)
    derived_open = len(body_open)
    derived_fixed = len(body_fixed)
    header_m = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', new_content)
    if header_m:
        h_open = int(header_m.group(2))
        h_fixed_clause = header_m.group(3)
        h_fixed = int(h_fixed_clause.split()[-1])
        if h_open != derived_open or h_fixed != derived_fixed:
            errors.append(f"Header/body mismatch: header {h_open}/{h_fixed} vs body {derived_open}/{derived_fixed}")
    else:
        errors.append("Header count line not found")

# B) Timestamp uniqueness
session_header_pat = f'### {timestamp} — Heartbeat Agent'
occ = new_content.count(session_header_pat)
if occ != 1:
    errors.append(f"Session timestamp appears {occ} times (expected 1)")

# C) Double separator collapse
if re.search(r'---\n\s*---\n', new_content):
    # Auto-fix
    new_content = re.sub(r'---\n\s*---\n', '---\n', new_content)
    # Re-write
    with open(temp_path, 'w') as f:
        f.write(new_content)
    print("[INFO] Collapsed double separators")

# D) Issue headings in Deployment section
deploy_match = re.search(r'\n## Deployment\n', new_content)
if deploy_match:
    after_deploy = new_content[deploy_match.end():deploy_match.end()+5000]
    stray = re.findall(r'\n### (ISSUE-\d+):', after_deploy)
    if stray:
        errors.append(f"ISSUE headings in Deployment section: {stray}")

# E) Last Reviewed freshness
if timestamp not in new_content:
    errors.append("Timestamp missing from Last Reviewed line")

# F) Session report placement: must be before Template
tmpl_match = re.search(r'\n## Template for New Issues', new_content)
sess_match = re.search(r'\n### ' + re.escape(timestamp) + r' — Heartbeat Agent', new_content)
if sess_match and tmpl_match:
    if sess_match.start() > tmpl_match.start():
        errors.append("Session report placed after Template section")
else:
    errors.append("Could not locate session report or Template section")

# If errors, restore and abort
if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(f"  - {e}")
    subprocess.run(['git', 'checkout', 'HEAD', '--', 'PLAYTEST-ISSUES.md'], capture_output=True)
    os.remove(temp_path)
    raise SystemExit(1)
else:
    # All good: move temp to final
    os.replace(temp_path, 'PLAYTEST-ISSUES.md')
    print("\nPLAYTEST-ISSUES.md updated successfully.")
    print(f"Open issues count: {derived_open}, Fixed: {derived_fixed}")
