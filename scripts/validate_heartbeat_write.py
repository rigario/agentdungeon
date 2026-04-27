
import re

with open("PLAYTEST-ISSUES.md",'r') as f:
    c = f.read()

errors = []

# 1. Derive open/fixed counts by scanning all ISSUE bodies
open_c = 0; fixed_c = 0
for m in re.finditer(r'### (ISSUE-\d+):', c):
    body_start = m.end()
    window = c[body_start:body_start+15000]
    nxt = re.search(r'\n### |\n## [A-Z]', window)
    body_end = body_start + (nxt.start() if nxt else 5000)
    body = c[body_start:body_end]
    if re.search(r'\*\*Fixed:\*\*', body):
        fixed_c += 1
    else:
        open_c += 1

hdr = re.search(r'(\*\*Open Issues:\*\* )(\d+) \| (\*\*Fixed Issues:\*\* \d+)', c)
if hdr:
    h_open = int(hdr.group(2)); h_fixed = int(hdr.group(3).split()[-1])
    if h_open != open_c or h_fixed != fixed_c:
        errors.append(f"Header mismatch: header {h_open}/{h_fixed} vs derived {open_c}/{fixed_c}")
    else:
        print(f"Header counts OK: Open={h_open}, Fixed={h_fixed}")
else:
    errors.append("Header line missing")

# 2. Session report placement and uniqueness
ts_pat = r'### 2026-04-27 \d{2}:\d{2} UTC — Heartbeat Agent'
ts_match = re.search(ts_pat, c)
if ts_match:
    print(f"Session header at pos {ts_match.start()}")
    count = len(re.findall(ts_pat, c))
    print(f"Occurrences: {count}")
    if count != 1:
        errors.append(f"Duplicate session timestamp (count={count})")
    # Check containment within PSR body
    psr_match = re.search(r'\n## Playtest Session Reports\n', c)
    psr_start = psr_match.end()
    next_h2 = re.search(r'\n## [A-Z]', c[psr_start:])
    psr_end = psr_start + (next_h2.start() if next_h2 else len(c)-psr_start)
    if psr_start <= ts_match.start() < psr_end:
        print("Session inside PSR body ✓")
    else:
        errors.append("Session outside PSR body")
else:
    errors.append("Session header not found")

# Is it first H3 in PSR body?
psr_match2 = re.search(r'\n## Playtest Session Reports\n(.*?)(\n## |$)', c, re.DOTALL)
if psr_match2:
    body = psr_match2.group(1)
    # Find first occurrence of our session header within body
    first_our = body.find('2026-04-27')
    if first_our != -1:
        # Check if any other H3 appears before it
        before = body[:first_our]
        other_h3 = re.search(r'\n### ', before)
        if other_h3:
            errors.append("Session not first in PSR body (older report appears first)")
        else:
            print("Session is first in PSR body ✓")
    else:
        errors.append("Session not found in PSR body substring")
else:
    errors.append("Could not parse PSR body")

# 3. Double separators
if re.search(r'---\n\s*---\n', c):
    errors.append("Double separators present")
else:
    print("No double separators ✓")

# 4. Last Reviewed freshness
if not re.search(r'\*\*Last Reviewed:\*\* 2026-04-27 \d{2}:\d{2} UTC', c):
    errors.append("Last Reviewed not updated to current run")
else:
    print("Last Reviewed fresh ✓")

print("\n=== ERRORS ===")
if errors:
    for e in errors:
        print(f" - {e}")
else:
    print("All validations passed")
