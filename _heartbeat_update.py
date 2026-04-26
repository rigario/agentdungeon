#!/usr/bin/env python3
import re, datetime, os, sys

ISSUES_PATH = 'PLAYTEST-ISSUES.md'
with open(ISSUES_PATH, 'r') as f:
    content = f.read()

now = datetime.datetime.now(datetime.timezone.utc)
timestamp_str = now.strftime('%Y-%m-%d %H:%M UTC')
char_id = "heartbeat-c-probe-c68c51"

print(f"Timestamp: {timestamp_str}")

# ---- Append evidence to ISSUE-017 ----
issue_hdr = '### ISSUE-017: World graph regression'
idx = content.find(issue_hdr)
if idx == -1:
    sys.exit("ISSUE-017 not found")

search_start = idx + 200
next_issue = content.find('\n### ISSUE-', search_start)
next_h2 = content.find('\n## Deployment\n', search_start)
candidates = [b for b in [next_issue, next_h2] if b > idx]
if not candidates:
    sys.exit("No boundary after ISSUE-017")
insert_at = min(candidates)

evidence = f"""

**Heartbeat Check ({timestamp_str} — World topology):**
    - Pre-flight: /health=200, /dm/health=200, /api/map/data total=12
    - Probe: {char_id}
    - All locations exits = None — zero connectivity
    - Conclusion: ISSUE-017 CONFIRMED — DB adjacency missing

"""

content = content[:insert_at] + evidence + content[insert_at:]

# ---- Re-find Template separator ----
tmpl_sep = '---\n\n## Template for New Issues'
idx_tmpl = content.find(tmpl_sep)
if idx_tmpl == -1:
    sys.exit("Template separator not found")

session = f"""---\n\n### {timestamp_str} — Heartbeat Agent — BLOCKED (ISSUE-017)

**Smoke:** 20/20 PASS | Infra: 200 all

**Blocker:** World exits all None (12/12). Explore yields [].

**Character:** {char_id}
- Create: location/current_location = rusty-tankard
- Move to thornhold: 200 success

**Scenario:** C — BLOCKED

**Reproduced:** ISSUE-017 (Open). Minor desync: move response current_location_id=None but GET correct.

**Next:** Reseed DB exits; redeploy; rerun Scenario C.

"""

content = content[:idx_tmpl] + session + content[idx_tmpl:]

# ---- Update Last Reviewed ----
new_lr = f"**Last Reviewed:** {timestamp_str} — Heartbeat — Smoke 20/20 PASS — Blocked ISSUE-017; Scenario C not executed"
content = re.sub(r'\*\*Last Reviewed:\*\* .*', new_lr, content, count=1)

# ---- Validate counts and fix header ----
open_match = re.search(r'\n## Open Issues\n', content)
open_start = open_match.end()
next_h2_sec = re.search(r'\n## [A-Z][^\n]*\n', content[open_start:])
open_body = content[open_start:open_start + (next_h2_sec.start() if next_h2_sec else len(content))]

body_open = []
body_fixed = []
for m in re.finditer(r'### (ISSUE-\d+):', open_body):
    body_start = m.end()
    nxt_i = re.search(r'\n### ISSUE-', open_body[body_start:])
    nxt_h = re.search(r'\n## [A-Z]', open_body[body_start:])
    ends = []
    if nxt_i: ends.append(body_start + nxt_i.start())
    if nxt_h: ends.append(body_start + nxt_h.start())
    b_end = min(ends) if ends else body_start + 5000
    ib = open_body[body_start:b_end]
    (body_fixed if re.search(r'\*\*Fixed:\*\*', ib) else body_open).append(m.group(1))

print(f"Body counts: open={len(body_open)}, fixed={len(body_fixed)}")

header_m = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', content)
if header_m:
    h_open = int(header_m.group(2)); h_fixed = int(header_m.group(3).split()[-1])
    if h_open != len(body_open) or h_fixed != len(body_fixed):
        new_h = f"**Open Issues:** {len(body_open)} | **Fixed Issues:** {len(body_fixed)}"
        content = content.replace(header_m.group(0), new_h, 1)
        print(f"Header repaired: {new_h}")

# ---- Double separator fix ----
content = re.sub(r'---\n\s*---\n', '---\n', content)

# ---- Timestamp uniqueness ----
if content.count(f"### {timestamp_str} — Heartbeat Agent") != 1:
    sys.exit("Duplicate timestamp")

# ---- Write ----
temp = ISSUES_PATH + '.tmp'
with open(temp, 'w') as f:
    f.write(content)
os.replace(temp, ISSUES_PATH)
print(f"\n✅ PLAYTEST-ISSUES.md updated successfully")
print(f"   Open: {len(body_open)}, Fixed: {len(body_fixed)}")
