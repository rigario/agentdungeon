#!/usr/bin/env python3
import re, datetime, os, sys

REPO = '/home/rigario/Projects/rigario-d20'
ISSUES = os.path.join(REPO, 'PLAYTEST-ISSUES.md')

now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Scenario A — BLOCKED"

with open(ISSUES, 'r') as f:
    content = f.read()

# Inject ISSUE-017 evidence
evidence = f"""

**Heartbeat Check ({ts} — World graph integrity):**
    - Endpoint: GET /api/map/data
    - Status: 200 OK, total = 10 (all required nodes present)
    - All locations have exits=None; connected_to field populated correctly.
    - Movement succeeded via connected_to; explore available_paths returns None.
    - Conclusion: ISSUE-017 CONFIRMED PERSISTENT — world-graph topology inconsistent.

"""

m = re.search(r'### ISSUE-017:', content)
if not m:
    print("ISSUE-017 not found", file=sys.stderr); sys.exit(1)
body_start = m.end()
nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', content[body_start:])
insert_at = body_start + nxt.start()
content = content[:insert_at] + evidence + content[insert_at:]
print(f"Injected evidence into ISSUE-017 at {insert_at}")

# Session report
session = f"""{session_header}

**Infrastructure:**
  /health:       200 OK
  /dm/health:    200 OK (dm_runtime ok, rules_server ok, narrator enabled)
  /api/map/data: 200 OK (10 locations, required nodes present)

**World Graph:**
  All locations exits=None; connected_to populated. Movement works; explore available_paths=None.
  Matches ISSUE-017 pattern — world-graph collapse (exits field not seeded).

**Smoke Suite:** 20/20 PASS

**Cadence:**
  Toggle→playtest (200), tick (total_ticks→1, is_active=1), toggle→normal (200).
  Doom clock advanced; cadence mechanics confirmed functional.

**Scenario:** A (Thornhold → forest-edge → cave-entrance chain)
**Outcome:** BLOCKED — ISSUE-017 prevents reliable navigation.
**Priority:** Redeploy with corrected world seed (populate exits from connected_to or regenerate adjacency from NARRATIVE-MAP.md).

"""

# Insert at PSR start
psr = re.search(r'\n## Playtest Session Reports\n', content)
if not psr:
    print("PSR section not found", file=sys.stderr); sys.exit(1)
after_psr = psr.end()
content = content[:after_psr] + "\n" + session + content[after_psr:]
print(f"Session report inserted at PSR start pos={after_psr}")

# Last Reviewed
new_lr = f"**Last Reviewed:** {ts} — Heartbeat — Smoke 20/20 PASS — ISSUE-017 confirmed"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)
print("Last Reviewed updated")

# Header reconciliation
open_c = fixed_c = 0
for m_i in re.finditer(r'### (ISSUE-\d+):', content):
    bs = m_i.end()
    nxt_i = re.search(r'\n### |\n## ', content[bs:])
    b = content[bs:bs+(nxt_i.start() if nxt_i else 5000)]
    if re.search(r'\*\*Fixed:\*\*', b):
        fixed_c += 1
    else:
        open_c += 1
m_head = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', content)
if m_head:
    new_head = f"{m_head.group(1)}{open_c} | **Fixed Issues:** {fixed_c}"
    content = content.replace(m_head.group(0), new_head, 1)
    print(f"Header reconciled: Open={open_c}, Fixed={fixed_c}")
else:
    print("Header pattern not found", file=sys.stderr)

content = re.sub(r'---\n\s*---\n', '---\n', content)
# Write temp
tmp = ISSUES + '.tmp'
with open(tmp, 'w') as f:
    f.write(content)

# Read temp for validation
with open(tmp, 'r') as f:
    newc = f.read()

# Normalize any double separators (pre-existing or introduced)
newc = re.sub(r'---\n\s*---\n', '---\n', newc)

errors = []
# Counts check
open_c2 = fixed_c2 = 0
for m_i in re.finditer(r'### (ISSUE-\d+):', newc):
    bs = m_i.end()
    nxt_i = re.search(r'\n### |\n## ', newc[bs:])
    b = newc[bs:bs+(nxt_i.start() if nxt_i else 5000)]
    if re.search(r'\*\*Fixed:\*\*', b):
        fixed_c2 += 1
    else:
        open_c2 += 1
m2 = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', newc)
if m2 and (int(m2.group(2)) != open_c2 or int(m2.group(3).split()[-1]) != fixed_c2):
    errors.append(f"Header/body mismatch: header {m2.group(2)}/{m2.group(3).split()[-1]} vs body {open_c2}/{fixed_c2}")

# Session placement
psr2 = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## |$)', newc, re.DOTALL)
if psr2:
    body = psr2.group(1)
    cnt = body.count(session_header)
    if cnt != 1:
        errors.append(f"Session header count in PSR body={cnt}")
else:
    errors.append("PSR body not found")

# Last Reviewed
if not re.search(rf'\*\*Last Reviewed:\*\* {ts}', newc):
    errors.append("Last Reviewed not updated")

# Double separators
double_count = len(re.findall(r'---\n\s*---\n', newc))
print(f"Debug: double separator count after normalization = {double_count}")
if double_count > 0:
    errors.append("Double separator sequence found")

# Report duplicate timestamps anywhere
if newc.count(session_header) != 1:
    errors.append("Duplicate session timestamp found")

if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(f"  - {e}")
    os.remove(tmp)
    sys.exit(1)
else:
    os.replace(tmp, ISSUES)
    print(f"\nPLAYTEST-ISSUES.md updated successfully at {ts}")
    print(f"Final counts: Open={open_c2}, Fixed={fixed_c2}")
    print("All post-write checks passed.")
