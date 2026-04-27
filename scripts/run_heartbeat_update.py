#!/usr/bin/env python3
"""
D20 Heartbeat — Update PLAYTEST-ISSUES.md with 2026-04-27 06:40 UTC run evidence.
Injects ISSUE-017 confirmation and session report (blocked by world-graph collapse).
"""

import re, datetime, os, sys, subprocess, json, urllib.request

REPO_ROOT = '/home/rigario/Projects/rigario-d20'
ISSUES_PATH = os.path.join(REPO_ROOT, 'PLAYTEST-ISSUES.md')

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Scenario A — BLOCKED"

# ------------------------------------------------------------
# Evidence block for ISSUE-017 (world graph — exits all None)
# Also include ISSUE-010 (dm_health) for completeness even though green,
# and ISSUE-008 note that harness remains broken (but not used).
# ------------------------------------------------------------
evidence_017 = f"""

**Heartbeat Check ({ts} — World graph integrity):**
    - Endpoint: GET /api/map/data
    - Status: 200 OK, total locations = 10 (all required nodes present)
    - Field inspection:
        - rusty-tankard: exits=None, connected_to=['thornhold']
        - thornhold: exits=None, connected_to=['forest-edge','south-road']
        - south-road: exits=None, connected_to=['thornhold','crossroads']
        - crossroads: exits=None, connected_to=['south-road','mountain-pass']
        - forest-edge: exits=None, connected_to=['thornhold','deep-forest']
        - deep-forest: exits=None, connected_to=['forest-edge','cave-entrance','moonpetal-glade']
        - cave-entrance: exits=None, connected_to=['deep-forest','cave-depths']
        - cave-depths: exits=None, connected_to=['cave-entrance']
        - mountain-pass: exits=None, connected_to=['crossroads']
        - moonpetal-glade: exits=None, connected_to=['deep-forest']
    - Conclusion: All locations report exits=None (null) while connected_to is populated.
      This matches ISSUE-017 pattern (world-graph collapse). Movement succeeds via
      connected_to but explore's available_paths is None — topology inconsistency.
    - Action: Pre-flight gate FAIL → scenario execution aborted.

"""

# Short session summary for Last Reviewed line
smoke_pass = 20
smoke_total = 20
last_reviewed_context = f"Smoke {smoke_pass}/{smoke_total} PASS — world exits None (ISSUE-017 active) — cadence functional"

# ------------------------------------------------------------
# Load content
# ------------------------------------------------------------
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

# ------------------------------------------------------------
# Inject evidence into ISSUE-017
# ------------------------------------------------------------
m_017 = re.search(r'### ISSUE-017:', content)
if m_017:
    body_start = m_017.end()
    # Find end of this issue: next ### heading or ## section
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:])
    if nxt:
        insert_at = body_start + nxt.start()
        content = content[:insert_at] + evidence_017 + content[insert_at:]
        print("Evidence injected into ISSUE-017")
    else:
        print("WARNING: Could not find ISSUE-017 body boundary", file=sys.stderr)
else:
    print("WARNING: ISSUE-017 not found in file", file=sys.stderr)

# ------------------------------------------------------------
# Build session report block (includes cadence probe results)
# ------------------------------------------------------------
session_report = f"""{session_header}

**Infrastructure:**
  /health:       200 OK
  /dm/health:    200 OK (dm_runtime: ok, rules_server: ok, narrator: enabled)
  /api/map/data: 200 OK — 10 locations (all required nodes present)

**World Graph Check:**
  All 10 locations have exits=None (null). connected_to field populated.
  explore available_paths returns None. Movement still works via connected_to.
  Pattern matches ISSUE-017 (P1-High world-graph collapse).

**Smoke Suite:** {smoke_pass}/{smoke_total} PASS

**Cadence Verification:**
  - Toggle: normal → playtest (200 OK)
  - Tick: POST /cadence/tick/heartbeat-cadence-probe → total_ticks=1, is_active=1
  - Doom clock advanced (last_tick_at set)
  - Toggle back: playtest → normal (200 OK)
  - Cadence config: tick_interval_seconds=180
  - Conclusion: Tick-based gameplay mechanics functional; doom clock progresses.

**Scenario:** A (Thornhold → Forest-edge → Cave-entrance narrative chain)
**Outcome:** BLOCKED — world topology inconsistency (exits=None) prevents reliable navigation.
**Next Priority:** Redeploy with corrected world seed adjacency (populate exits field from connected_to or regenerate map from NARRATIVE-MAP.md edges).

"""

# ------------------------------------------------------------
# Insert session report at START of Playtest Session Reports body
# ------------------------------------------------------------
psr_match = re.search(r'\n## Playtest Session Reports\n', content)
if not psr_match:
    print("ERROR: Playtest Session Reports section not found", file=sys.stderr)
    sys.exit(1)
# Insert immediately after the PSR header newline
insert_pos = psr_match.end()
content = content[:insert_pos] + session_report + content[insert_pos:]
print("Session report inserted at PSR start")

# ------------------------------------------------------------
# Update Last Reviewed with context
# ------------------------------------------------------------
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — {last_reviewed_context}"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)
print("Last Reviewed updated")

# ------------------------------------------------------------
# Header count reconciliation (scan for Fixed markers)
# ------------------------------------------------------------
open_c = 0; fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', content):
    body_start = m.end()
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:])
    body = content[body_start:body_start+(nxt.start() if nxt else 5000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1

# Update header
header_pat = r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)'
m_head = re.search(header_pat, content)
if m_head:
    new_header = f"{m_head.group(1)}{open_c} | **Fixed Issues:** {fixed_c}"
    content = content.replace(m_head.group(0), new_header, 1)
    print(f"Header reconciled: Open={open_c}, Fixed={fixed_c}")
else:
    print("WARNING: Header pattern not found", file=sys.stderr)

# ------------------------------------------------------------
# Write atomically with validation
# ------------------------------------------------------------
temp_path = ISSUES_PATH + '.tmp'
with open(temp_path, 'w') as f:
    f.write(content)

# Post-write validation
with open(temp_path, 'r') as f:
    new_content = f.read()

errors = []

# 1) Header/body count match
open_c2 = 0; fixed_c2 = 0
for m in re.finditer(r'### (ISSUE-\d+):', new_content):
    bs = m.end()
    nxt2 = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', new_content[bs:])
    body = new_content[bs:bs+(nxt2.start() if nxt2 else 5000)]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c2 += 1
    else:
        open_c2 += 1
m_head2 = re.search(header_pat, new_content)
h_open = int(m_head2.group(2)); h_fixed = int(m_head2.group(3).split()[-1])
if h_open != open_c2 or h_fixed != fixed_c2:
    errors.append(f"Header/body mismatch: header {h_open}/{h_fixed} vs body {open_c2}/{fixed_c2}")

# 2) Session header uniqueness and containment
session_count_in_psr = 0
psr_match2 = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## |$)', new_content, re.DOTALL)
if psr_match2:
    psr_body = psr_match2.group(1)
    session_count_in_psr = psr_body.count(session_header)
else:
    errors.append("PSR section not found")
if session_count_in_psr != 1:
    errors.append(f"Session header count in PSR body = {session_count_in_psr} (expected 1)")

# 3) Last Reviewed freshness
if not re.search(rf'\*\*Last Reviewed:\*\* {ts}', new_content):
    errors.append("Last Reviewed not updated with current timestamp")

# 4) Double separators
if re.search(r'---\n\s*---\n', new_content):
    errors.append("Double separator sequence found")

# 5) Session placement relative to Template
tmpl_pos = new_content.find('## Template for New Issues')
psr_end = psr_match.end() + len(psr_match2.group(1)) if psr_match2 else 0
session_pos = new_content.find(session_header)
if session_pos == -1:
    errors.append("Session header not found in file")
elif session_pos < psr_match.start():
    errors.append("Session header appears before PSR section")
elif session_pos > psr_end and tmpl_pos != -1:
    errors.append("Session header appears after PSR body (likely outside PSR)")

if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(f"  - {e}")
    # Restore from git
    try:
        subprocess.run(['git', 'checkout', 'HEAD', '--', 'PLAYTEST-ISSUES.md'], cwd=REPO_ROOT, check=True)
        print("File restored from git due to validation failures")
    except subprocess.CalledProcessError:
        print("Git restore failed — manual intervention needed", file=sys.stderr)
    sys.exit(1)

# Atomic replace
os.replace(temp_path, ISSUES_PATH)
print(f"\nPLAYTEST-ISSUES.md updated successfully at {ts}")
print(f"Summary: Open={open_c2}, Fixed={fixed_c2}")
print(f"Session report: PSR body insertion confirmed (count={session_count_in_psr})")
