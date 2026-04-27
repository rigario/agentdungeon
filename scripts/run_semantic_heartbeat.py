#!/usr/bin/env python3
"""
D20 Semantic Guard Heartbeat — Fixed version
"""

import os, sys, re, json, datetime, urllib.request, urllib.error, subprocess

REPO_ROOT = '/home/rigario/Projects/rigario-d20'
RULES_URL = os.environ.get('RULES_URL', 'https://d20.holocronlabs.ai')
DM_URL = os.environ.get('DM_URL', 'https://d20.holocronlabs.ai')
ISSUES_PATH = os.path.join(REPO_ROOT, 'PLAYTEST-ISSUES.md')

def http_post(url, payload_dict, timeout=10):
    try:
        data = json.dumps(payload_dict).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST',
                                     headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try: return e.code, json.loads(body)
        except: return e.code, body
    except Exception as e:
        return f"EXC:{type(e).__name__}", str(e)[:200]

def http_get(url, timeout=10):
    try:
        req = urllib.request.Request(url, method='GET')
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, body[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')[:200]
    except Exception as e:
        return f"EXC", str(e)[:200]

def load_file(path):
    with open(path, 'r') as f:
        return f.read()

BLOCK_CASES = [
    "I don't want to go to the woods", "do not go to the woods", "avoid the woods",
    "I refuse to enter the cave", "stay away from Whisperwood", "not going to the cave",
    "don't attack the wolves", "dont rest here", "I will not attack the wolves",
    "let us not go to the woods", "do not open the door",
]
ALLOW_CASES = [
    "tell Aldric I don't want to go to the woods", "ask Aldric if I should avoid the woods",
    "I want to go to the woods", "go to the woods", "the door dont open easily",
]

def check_block_response(resp):
    if not isinstance(resp, dict): return False, f"Non-JSON: {str(resp)[:100]}"
    cls = resp.get('classification')
    if not isinstance(cls, dict): return False, f"No classification"
    details = cls.get('details', {})
    guard = details.get('_semantic_guard', False)
    action_type = cls.get('action_type')
    reason = details.get('_semantic_guard_reason', '')
    if cls.get('type') == 'general' and action_type is None and guard:
        if 'negated_or_refusal_action' in str(reason).lower(): return True, "Blocked"
        return False, f"Guard reason: {reason}"
    return False, f"type={cls.get('type')}, action_type={action_type}, guard={guard}"

def check_allow_response(resp):
    if not isinstance(resp, dict): return False, f"Non-JSON: {str(resp)[:100]}"
    cls = resp.get('classification')
    if not isinstance(cls, dict): return False, "No classification"
    details = cls.get('details', {})
    guard = details.get('_semantic_guard', False)
    action_type = cls.get('action_type')
    if guard: return False, f"False positive guard={guard}"
    if action_type is None: return False, "action_type null"
    return True, f"action_type={action_type}"

def find_issue_by_keyword(content, keywords):
    for m in re.finditer(r'### (ISSUE-\d+):', content):
        iid = m.group(1)
        body_start = m.end()
        window = content[body_start:body_start+2000]
        for kw in keywords:
            if re.search(kw, window, re.IGNORECASE):
                return iid
    return None

def inject_evidence(content, issue_id, evidence_block):
    pos_match = re.search(r'### ' + re.escape(issue_id) + r':', content)
    if not pos_match: return content, False
    body_start = pos_match.end()
    window = content[body_start:body_start+15000]
    nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', window)
    if not nxt: return content, False
    insert_at = body_start + nxt.start()
    if content[insert_at-1:insert_at] != '\n':
        evidence_block = '\n' + evidence_block
    return content[:insert_at] + evidence_block + content[insert_at:], True

def insert_session_at_top(content, session_md):
    psr_header = '\n## Playtest Session Reports\n'
    psr_match = content.find(psr_header)
    if psr_match == -1: raise RuntimeError("Playtest Session Reports section not found")
    after_header = content[psr_match + len(psr_header):]
    first_h3 = re.search(r'\n### [0-9]{4}-[0-9]{2}-[0-9]{2}', after_header)
    if first_h3:
        insert_at = psr_match + len(psr_header) + first_h3.start()
    else:
        insert_at = psr_match + len(psr_header)
    return content[:insert_at] + session_md + content[insert_at:]

def reconcile_header_counts(content):
    open_c = 0; fixed_c = 0
    for m in re.finditer(r'### (ISSUE-\d+):', content):
        body_start = m.end()
        window = content[body_start:body_start+5000]
        nxt = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', window)
        body = content[body_start:body_start+(nxt.start() if nxt else 5000)]
        if re.search(r'\*\*Fixed:\*\*', body): fixed_c += 1
        else: open_c += 1
    new_header = f"**Open Issues:** {open_c} | **Fixed Issues:** {fixed_c}"
    new_content = re.sub(r'\*\*Open Issues:\*\* \d+ \| \*\*Fixed Issues:\*\* \d+', new_header, content, count=1)
    return new_content, open_c, fixed_c

def main():
    print("=" * 60)
    print("D20 SEMANTIC COHERENCE GUARD HEARTBEAT")
    print("=" * 60)
    now = datetime.datetime.now(datetime.timezone.utc)
    ts = now.strftime('%Y-%m-%d %H:%M UTC')
    session_header = f"### {ts} — Semantic Heartbeat —"

    # Phase 1: Health
    print("\n[PHASE 1] Infrastructure health...")
    h_health = http_get(f"{RULES_URL}/health")
    h_dm = http_get(f"{DM_URL}/dm/health")
    h_map = http_get(f"{RULES_URL}/api/map/data")
    print(f"  /health: {h_health[0]}")
    print(f"  /dm/health: {h_dm[0]}")
    print(f"  /api/map/data: {h_map[0]}")
    infra_ok = (h_health[0] == 200 and h_dm[0] == 200 and h_map[0] == 200)

    # Phase 2: Intent probes
    print("\n[PHASE 2] Intent analysis...")
    block_fail = []; allow_fail = []
    if infra_ok:
        for text in BLOCK_CASES:
            code, resp = http_post(f"{DM_URL}/dm/intent/analyze", {"message": text})
            if code != 200:
                block_fail.append((text, f"HTTP {code}", None))
                print(f"  BLOCK '{text[:45]}' → FAIL — HTTP {code}")
            else:
                passed, reason = check_block_response(resp)
                if not passed: block_fail.append((text, reason, resp))
                print(f"  BLOCK '{text[:45]}' → {'PASS' if passed else 'FAIL'} — {reason}")
        for text in ALLOW_CASES:
            code, resp = http_post(f"{DM_URL}/dm/intent/analyze", {"message": text})
            if code != 200:
                allow_fail.append((text, f"HTTP {code}", None))
                print(f"  ALLOW '{text[:45]}' → FAIL — HTTP {code}")
            else:
                passed, reason = check_allow_response(resp)
                if not passed: allow_fail.append((text, reason, resp))
                print(f"  ALLOW '{text[:45]}' → {'PASS' if passed else 'FAIL'} — {reason}")
    else:
        print("  SKIPPED — infra down")

    # Phase 3: Narrate check
    print("\n[PHASE 3] No-mutation narration...")
    narrate_ok = False
    if infra_ok:
        world_context = {"current_location_id": "thornhold", "known_locations": ["thornhold","forest-edge"], "connections": {"thornhold": ["forest-edge"]}}
        payload = {"player_message": "I don't want to go to the woods", "resolved_result": {"action_type": None, "success": True}, "world_context": world_context, "character_id": "probe-sem-001"}
        code, narr = http_post(f"{DM_URL}/dm/narrate", payload)
        if code == 200 and isinstance(narr, dict):
            narration = narr.get('narration', {})
            npc_lines = narr.get('npc_lines')
            trace = narr.get('server_trace', {})
            intent_used = trace.get('intent_used', {})
            guard_flag = intent_used.get('details', {}).get('_semantic_guard', False)
            nar_scene = narration.get('scene', '') if isinstance(narration, dict) else str(narration)
            print(f"  Narration: {nar_scene[:120]}")
            print(f"  NPC lines: {npc_lines}")
            print(f"  Guard: {guard_flag}")
            if guard_flag and (npc_lines is None or npc_lines == []):
                narrate_ok = True
                print("  → PASS")
            else:
                print("  → FAIL")
        else:
            print(f"  → FAIL: HTTP {code} | {str(narr)[:100]}")
    else:
        print("  SKIPPED")

    # Phase 4: Local tests
    print("\n[PHASE 4] Local regression tests...")
    test_results = None
    test_files = [os.path.join(REPO_ROOT, 'tests', p) for p in ['test_intent_router.py','test_dm_runtime_synthesis.py']]
    if all(os.path.exists(p) for p in test_files):
        proc = subprocess.run(["python3", "-m", "pytest"] + test_files + ["-q","--tb=short"],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
        test_results = {'passed': proc.stdout.count(' PASSED'), 'failed': proc.stdout.count(' FAILED'), 'output': proc.stdout[-800:]}
        print(f"  Tests: {test_results['passed']}P/{test_results['failed']}F")
    else:
        print("  Tests not found — skipping")

    # Phase 5: Determine regression
    semantic_fail = (
        infra_ok and (
            len(block_fail) > 0 or
            len(allow_fail) > 0 or
            not narrate_ok or
            (test_results and test_results['failed'] > 0)
        )
    )
    print("\n[PHASE 5] Assessment...")
    if semantic_fail: print("  REGRESSION DETECTED")
    elif not infra_ok: print("  INFRA BLOCK — semantic not tested")
    else: print("  ALL CHECKS PASSED")

    # Phase 6: Update PLAYTEST-ISSUES.md
    if not os.path.exists(ISSUES_PATH):
        print("\n  PLAYTEST-ISSUES.md not found — skipping file update")
    else:
        content = load_file(ISSUES_PATH)
        # If regression, add evidence to issue
        if semantic_fail:
            print("\n[PHASE 6] Adding evidence to issues log...")
            issue_id = find_issue_by_keyword(content, ['semantic.*guard','intent.*analyze','negated','refusal'])
            if issue_id:
                print(f"  Appending to {issue_id}")
            else:
                nums = [int(re.search(r'ISSUE-(\d+)', m.group(1)).group(1)) for m in re.finditer(r'### ISSUE-(\d+):', content)]
                next_num = max(nums) + 1 if nums else 1
                issue_id = f"ISSUE-{next_num:03d}"
                print(f"  Creating new issue: {issue_id}")
            evidence_lines = [f"**Heartbeat Check ({ts} — Semantic Guard):**","",
                f"Health: /health={h_health[0]}, /dm_health={h_dm[0]}, map={h_map[0]}"]
            if block_fail:
                evidence_lines.append(f"**Block failures:** {len(block_fail)}/{len(BLOCK_CASES)}")
                for text, reason, resp in block_fail[:5]:
                    snippet = json.dumps(resp)[:120] if resp else reason
                    evidence_lines.append(f"    - '{text[:60]}' → {reason}")
                    evidence_lines.append(f"      {snippet}")
            if allow_fail:
                evidence_lines.append(f"**Allow failures:** {len(allow_fail)}/{len(ALLOW_CASES)}")
                for text, reason, resp in allow_fail[:5]:
                    snippet = json.dumps(resp)[:120] if resp else reason
                    evidence_lines.append(f"    - '{text[:60]}' → {reason}")
                    evidence_lines.append(f"      {snippet}")
            if not narrate_ok:
                evidence_lines.append("**Narrate:** FAILED — guard not blocking")
            if test_results and test_results['failed'] > 0:
                evidence_lines.append(f"**Local tests:** {test_results['failed']} failures")
                evidence_lines.append(test_results['output'][:300])
            evidence_block = "\n".join(evidence_lines) + "\n"
            content, ok = inject_evidence(content, issue_id, evidence_block)
            if not ok:
                # Create new issue in Open Issues
                open_match = re.search(r'\n## Open Issues\n', content)
                if open_match:
                    after_open = content[open_match.end():]
                    next_h2 = re.search(r'\n## [A-Z][^\n]*\n', after_open)
                    insert_at = open_match.end() + (next_h2.start() if next_h2 else len(after_open))
                    content = content[:insert_at] + f"\n### {issue_id}:\n**Status:** OPEN\n\n**Summary:** Semantic guard regression — negation not blocking actions\n\n**Evidence:**\n{evidence_block}\n" + content[insert_at:]
                    print(f"  Inserted new issue before next section")
                else:
                    print("  ERROR: Open Issues section not found")
            # else evidence injected into existing issue

        # Always append session report (newest-first)
        print("\n[PHASE 7] Appending session report...")
        if semantic_fail:
            outcome = "REGRESSION — evidence recorded"
        elif not infra_ok:
            outcome = "BLOCKED — infra failure"
        else:
            outcome = "ALL CLEAR — guard operational"
        session_md = f"""{session_header} {outcome}

**Infrastructure:**
  /health:       {h_health[0]} {h_health[1][:80]}
  /dm_health:    {h_dm[0]} {h_dm[1][:80]}
  /api/map/data: {h_map[0]} {h_map[1][:80]}

**Semantic Gate ({'active' if infra_ok else 'skipped'}):**
  Block: {len(block_fail)}/{len(BLOCK_CASES)} failed
  Allow: {len(allow_fail)}/{len(ALLOW_CASES)} failed
  Narrate: {"PASS" if narrate_ok else "FAIL"}
  Local tests: {test_results['passed'] if test_results else 'N/A'}P/{test_results['failed'] if test_results else 'N/A'}F

**Outcome:** {outcome}
"""
        content = insert_session_at_top(content, session_md)

        # Update Last Reviewed
        content = re.sub(r'\*\*Last Reviewed:\*\* .*',
                         f"**Last Reviewed:** {ts} — Semantic Heartbeat — {'regression' if semantic_fail else 'OK'}",
                         content, count=1)

        # Reconcile Open/Fixed counts
        content, open_c, fixed_c = reconcile_header_counts(content)

        # Atomic write with validation
        tmp_path = ISSUES_PATH + '.tmp'
        with open(tmp_path, 'w') as f:
            f.write(content)
        with open(tmp_path, 'r') as f:
            validate = f.read()
        errors = []
        if validate.count(session_header) != 1:
            errors.append("Duplicate session header")
        if re.search(r'---\n\s*---\n', validate):
            errors.append("Double separator")
        open_bodies = 0; fixed_bodies = 0
        for m in re.finditer(r'### (ISSUE-\d+):', validate):
            bstart = m.end()
            window = validate[bstart:bstart+5000]
            nxt_m = re.search(r'\n### (ISSUE-\d+):|\n## [A-Z]', window)
            body = validate[bstart:bstart+(nxt_m.start() if nxt_m else 5000)]
            if re.search(r'\*\*Fixed:\*\*', body): fixed_bodies += 1
            else: open_bodies += 1
        header_m = re.search(r'\*\*Open Issues:\*\* (\d+) \| \*\*Fixed Issues:\*\* (\d+)', validate)
        if header_m and (int(header_m.group(1)) != open_bodies or int(header_m.group(2)) != fixed_bodies):
            errors.append(f"Count mismatch: header {header_m.group(1)}O/{header_m.group(2)}F vs body {open_bodies}O/{fixed_bodies}F")
        if errors:
            print("  Validation errors:")
            for e in errors: print(f"    - {e}")
            os.remove(tmp_path)
            print("  Aborted — file unchanged")
        else:
            os.replace(tmp_path, ISSUES_PATH)
            print(f"  File updated: Open={open_bodies}, Fixed={fixed_c}")

    # Final report
    print("\n" + "=" * 60)
    print("FINAL REPORT — For Discord")
    print("=" * 60)
    print(f"Time:       {ts}")
    print(f"Infra:      health={h_health[0]} dm={h_dm[0]} map={h_map[0]}")
    print(f"Status:     {'REGRESSION' if semantic_fail else ('INFRA BLOCK' if not infra_ok else 'OK')}")
    print(f"  Block:    {len(block_fail)}/{len(BLOCK_CASES)} failed")
    print(f"  Allow:    {len(allow_fail)}/{len(ALLOW_CASES)} failed")
    print(f"  Narrate:  {'PASS' if narrate_ok else 'FAIL'}")
    print(f"  Local:    {test_results['passed'] if test_results else 'N/A'}P/{test_results['failed'] if test_results else 'N/A'}F")
    if semantic_fail:
        print("\nAction required: Semantic guard regression — evidence appended to PLAYTEST-ISSUES.md")
    else:
        print("\nNo action required — guard functioning correctly")
    return 0

if __name__ == '__main__':
    sys.exit(main())
