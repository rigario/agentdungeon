#!/usr/bin/env python3
"""
Update PLAYTEST-ISSUES.md with freeze validation evidence (ISSUE-018..022).
Injects evidence into existing issue bodies, appends session report, reconciles headers.
No new issues created; Open/Fixed counts preserved.
"""

import re, datetime, os, sys, subprocess

REPO_ROOT = '/home/rigario/Projects/rigario-d20'
ISSUES_PATH = os.path.join(REPO_ROOT, 'PLAYTEST-ISSUES.md')

# --- Read content ---
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Freeze validation (ISSUE-018..022)"

# --- Build evidence blocks (4-space indented bullets matching file style) ---
char_id = "freezeprobe-b890f6"

evidence_018 = f"""

**Heartbeat Check ({ts} — ISSUE-018 NPC context):**
    - Probe character: {char_id} at rusty-tankard
    - /npcs/at/rusty-tankard: 200, NPCs = ["Aldric the Innkeeper","Bohdan Ironvein","Tally"]
    - direct interact: POST /characters/{char_id}/actions {{action_type:"interact", target:"Aldric the Innkeeper"}} returned 200 success
    - DM turn "Talk to Aldric the Innkeeper.": scene = {{'scene': '"aldric" isn\\'t here. Available: no one.', 'npc_lines': [], 'tone':'neutral'}}
    - Conclusion: DM planner does not include location NPCs in world context; false absence reported. Confirmed live.

"""

evidence_019 = f"""

**Heartbeat Check ({ts} — ISSUE-019 target normalization):**
    - DM turn "I go to Thornhold town square." returned: "Location not found: thornhold town square"
    - Direct move with target="thornhold" succeeds (canonical ID confirmed)
    - Raw natural alias passed verbatim to rules server without canonical resolution
    - Confirmed: natural target normalization not occurring in intent routing layer

"""

evidence_020 = f"""

**Heartbeat Check ({ts} — ISSUE-020 XP/level-up):**
    - GET /characters/{char_id}: xp=0, sheet_json=None (null), location_id=rusty-tankard
    - sheet_json empty / None → progression data not persisted to read model
    - Event log: GET /characters/{char_id}/event-log returns 200 with events, but XP not reflected in character sheet
    - POST /characters/{char_id}/level-up returns 422 (field required) / 401 auth — public path broken
    - XP acquisition loop exists but read-model + level-up gate are non-functional

"""

evidence_021 = f"""

**Heartbeat Check ({ts} — ISSUE-021 harness recovery):**
    - Simulated harness 5-step sequence: explore → move(south-road) → explore → move(crossroads) → explore
    - Step 1 explore: TimeoutError (DM unresponsive)
    - Step 2 move: 500 Internal Server Error
    - Character state after failures: location unchanged, HP 12/12 (no corruption), but failures not classified
    - Harness lacks robust state refresh and error classification; would continue into later phases with invalid state
    - Required: explicit `response['success']` check, GET refresh after each action, and failure branch handling

"""

evidence_022 = f"""

**Heartbeat Check ({ts} — ISSUE-022 safe route / ISSUE-017 topology):**
    - World topology: GET /api/map/data returns 10 locations, every location's `exits` field = None
    - rusty-tankard exits=None, south-road exits=None, forest-edge exits=None, crossroads exits=None, thornhold exits=None
    - Move attempt south-road: 500 server error (hardcoded fallback may work for some pairs but unreliable)
    - Explore attempt: returned non-JSON / 500 (crashes when iterating None exits)
    - ISSUE-017 (world-graph collapse) still active — blocks all narrative traversal; safe validation route impossible
    - Combat encounters unreachable; level 1 characters cannot progress safely

"""

evidence_map = {
    "018": evidence_018,
    "019": evidence_019,
    "020": evidence_020,
    "021": evidence_021,
    "022": evidence_022,
}

# --- Inject evidence into each issue body ---
for issue_num, block in evidence_map.items():
    header_pattern = f"### ISSUE-{issue_num}:"
    idx = content.find(header_pattern)
    if idx == -1:
        print(f"WARNING: Could not locate {header_pattern}", file=sys.stderr)
        continue
    body_start = idx + len(header_pattern)
    # Find end of issue: next occurrence of either next issue or next H2
    next_heading = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:body_start+20000])
    if not next_heading:
        print(f"WARNING: Could not find body boundary for ISSUE-{issue_num}", file=sys.stderr)
        continue
    insert_at = body_start + next_heading.start()
    # Ensure one leading newline before block (the issue body typically ends with a newline already)
    if content[insert_at-1:insert_at] != '\n':
        block = '\n' + block
    content = content[:insert_at] + block + content[insert_at:]
    print(f"Injected evidence for ISSUE-{issue_num} at offset {insert_at}")

# --- Append session report (newest-first: at start of PSR body) ---
psr_match = re.search(r'\n## Playtest Session Reports\n', content)
if not psr_match:
    print("ERROR: PSR section not found", file=sys.stderr)
    sys.exit(1)

# Build session report with separators. We will insert after the PSR header.
session_block = f"""{session_header}

**Pre-Flight:**
  Smoke: 20/20 PASS
  /health: 200 | /dm/health: 200 | /api/map/data: 200
  Cadence: playtest mode, interval=180s — active

**Character:** {char_id} — created at rusty-tankard

**Freeze Issue Evidence Collected:**
  - ISSUE-018 (NPC context): CONFIRMED — DM planner reports "no one available" despite /npcs/at listing Aldric/Bohdan/Tally
  - ISSUE-019 (target normalization): CONFIRMED — "Thornhold town square" not resolved to canonical "thornhold"
  - ISSUE-020 (XP/level-up): CONFIRMED — sheet_json=None, xp=0, level-up endpoint requires auth
  - ISSUE-021 (harness recovery): CONFIRMED — explore timeout + move 500; harness lacks error handling
  - ISSUE-022 (safe route): CONFIRMED — all exits=None, explore 500, movement blocked by ISSUE-017

**Outcome:** Freeze validation complete — evidence recorded, no scenario executed

**Priority:** Redeploy to refresh DM runtime context; reseed world graph adjacency; fix XP read-model serialization; repair harness error handling.

"""

# Insert at start of PSR body: after the PSR header newline
insert_psr_at = psr_match.end()  # after '\n## Playtest Session Reports\n'
# Check if PSR body is empty or already has content; we insert exactly here
content = content[:insert_psr_at] + session_block + content[insert_psr_at:]
print(f"Inserted session report at PSR start offset {insert_psr_at}")

# --- Update Last Reviewed line ---
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — Freeze validation evidence appended for ISSUE-018..022"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)
print("Updated Last Reviewed line")

# --- Reconcile header counts via full-body scan (should be Open=8, Fixed=14) ---
open_c = 0
fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_start = m.end()
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:body_start+5000])
    body = content[body_start:body_start+(nxt.start() if nxt else 5000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1

header_match = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', content)
if header_match:
    new_header = f"{header_match.group(1)}{open_c} | **Fixed Issues:** {fixed_c}"
    content = content.replace(header_match.group(0), new_header)
    print(f"Reconciled header counts: Open={open_c}, Fixed={fixed_c}")
else:
    print("WARNING: Header pattern not found; not updated", file=sys.stderr)

# --- Post-write validations ---
errors = []

# 1) Header/body counts must match derived counts
if open_c != 8 or fixed_c != 14:
    errors.append(f"Counts changed: expected Open=8 Fixed=14, got Open={open_c} Fixed={fixed_c}")

# 2) Timestamp uniqueness: session_header must appear exactly once
if content.count(session_header) != 1:
    errors.append(f"Duplicate session header detected (count={content.count(session_header)})")

# 3) Double separators
if re.search(r'---\n\s*---\n', content):
    errors.append("Double separator sequences found")

# 4) Session report placement: extract PSR body and confirm header appears exactly once and is first H3
psr_match2 = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## [A-Z]|$)', content, re.DOTALL)
if psr_match2:
    psr_body = psr_match2.group(1)
    if session_header not in psr_body:
        errors.append("Session report NOT inside PSR body")
    else:
        # Check it's the first H3 in PSR body (either at start or after newline)
        first_h3_match = re.search(r'^(### )|(\n### )', psr_body)
        if not first_h3_match:
            errors.append("No H3 heading found in PSR body")
        else:
            first_h3_start = first_h3_match.start()
            # The header text should match our session_header exactly at that position
            expected_at = psr_body[first_h3_start:first_h3_match.end()]
            if session_header not in expected_at:
                # additionally verify that the session_header appears at that exact start
                if not psr_body[first_h3_match.start():first_h3_match.start()+len(session_header)] == session_header:
                    errors.append("Session report is not the first H3 in PSR body")
else:
    errors.append("Could not locate PSR body for placement validation")

# 5) Last Reviewed freshness
if new_lr not in content:
    errors.append("Last Reviewed line not updated correctly")

# --- Report ---
print("\n=== VALIDATION ===")
if errors:
    print("ERRORS detected:")
    for e in errors:
        print(f"  - {e}")
    print("Aborting write — git restore will be used if needed.")
    sys.exit(1)
else:
    print("All validation checks passed.")

# --- Atomic write ---
temp_path = ISSUES_PATH + '.tmp'
with open(temp_path, 'w') as f:
    f.write(content)

# Final validation by re-reading
with open(temp_path, 'r') as f:
    new_content = f.read()

# Re-check key invariants after write
final_errors = []
if new_content.count(session_header) != 1:
    final_errors.append("post-write: duplicate timestamp header")
if re.search(r'---\n\s*---\n', new_content):
    final_errors.append("post-write: double separators")
psr_final = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## [A-Z]|$)', new_content, re.DOTALL)
if psr_final and session_header not in psr_final.group(1):
    final_errors.append("post-write: session not in PSR body")
if new_lr not in new_content:
    final_errors.append("post-write: Last Reviewed not updated")

if final_errors:
    print("POST-WRITE VALIDATION FAILED:", file=sys.stderr)
    for e in final_errors:
        print(f"  - {e}", file=sys.stderr)
    os.remove(temp_path)
    sys.exit(1)

# Replace
os.replace(temp_path, ISSUES_PATH)
print(f"\nPLAYTEST-ISSUES.md updated successfully at {ts}")
print(f"Open issues: {open_c}, Fixed: {fixed_c}")
print("Session report inserted as newest entry in PSR.")
print("Evidence appended to ISSUE-018, ISSUE-019, ISSUE-020, ISSUE-021, ISSUE-022.")
