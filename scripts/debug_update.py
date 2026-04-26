import datetime, re

ISSUES_PATH = "PLAYTEST-ISSUES.md"
now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%d %H:%M UTC')
session_header = f"### {ts} — Heartbeat Agent — Semantic Guard Verification"

with open(ISSUES_PATH, 'r') as f:
    lines = f.readlines()

print(f"Total lines before edit: {len(lines)}")
print(f"Line 3: {repr(lines[2])}")
print(f"Line 688: {repr(lines[687])}")
print(f"Line 1092 (expected ## Deployment): {repr(lines[1091])}")
print(f"Line 1098 (PSR header): {repr(lines[1097])}")

# Check for PSR header
psr_candidates = [(i,l) for i,l in enumerate(lines) if "Playtest Session Reports" in l]
print(f"PSR header candidates: {[(i, repr(l)) for i,l in psr_candidates]}")

deploy_candidates = [(i,l) for i,l in enumerate(lines) if l.strip() == "## Deployment"]
print(f"Deployment header: {deploy_candidates}")
