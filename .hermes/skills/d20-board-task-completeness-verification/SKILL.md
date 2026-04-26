---
trigger_conditions:
  - "D20 heartbeat task selection"
  - "Mission Control task status verification"
  - "acceptance criteria validation"
  
purpose: "Systematically verify whether a Mission Control task (To Do or Done) is *genuinely complete* per acceptance criteria, or board-stale/partially-implemented. Catches gaps where backend is complete but frontend rendering is partial, or where commits exist but acceptance criteria aren't fully satisfied."
  
steps:
  - description: "Pull live board context from heartbeat API"
    commands: []
    note: "GET http://vps-8432193b:8500/api/context/heartbeat/{config_id}"
    
  - description: "Identify candidate actionable tasks by priority/deps"
    commands: []
    note: "Filter: status in (To Do, In Progress), all depends_on == Done, not Blocked, executable type"
    
  - description: "Git history check — locate commits referencing task ID"
    commands:
      - "git log --oneline --grep <task_id>"
      - "git show --stat <commit_sha>"
    note: "Confirm commit message references task, files changed match scope"
    
  - description: "Backend implementation audit"
    commands:
      - "grep -rn 'def <key_function>' app/"
      - "grep -n '<field>' app/scripts/seed.py"
    note: "Functions defined? Schema updated? Seeds inserted?"
    
  - description: "API endpoint payload verification"
    commands: []
    note: "Inspect router code: does endpoint return required fields for both public and character-scoped paths?"
    
  - description: "Frontend template rendering check (common gap)"
    commands:
      - "grep -n '<field>' app/static/<page>.html"
      - "grep -n '.css-class' app/static/<page>.html"
    note: "Backend data present but not rendered? CSS class defined?"
    
  - description: "Test coverage and result check"
    commands:
      - "python -m pytest tests/test_<feature>.py -v"
    note: "Distinguish env-only failures (ConnectionRefused) from code failures"
    
  - description: "Acceptance criteria checklist"
    note: "Read task.acceptance verbatim. Mark each bullet ✅ or ❌ explicitly."
    
  - description: "Board-status contradiction detection"
    decision_points:
      - "Code Done but board To Do? → MC board stale (patch needed)"
      - "Code partial but board Done? → Mis-marked (log contradiction)"
      - "Both Done? → Clean"

common_gap_patterns:
  - pattern: "Data-return-but-not-rendered"
    symptom: "API returns field (e.g., personality) but HTML template doesn't display it"
    fix: "Add template interpolation + CSS"
    
  - pattern: "Single-path working, multi-path stubbed"
    symptom: "Backend logic exists but UI still uses random/default selection"
    fix: "Update frontend choice rendering logic"
    
  - pattern: "Service defined but not wired"
    symptom: "Function exists in services/ but never called in any endpoint"
    fix: "Wire into router"
    
  - pattern: "CSS missing for new field"
    symptom: "Text renders unstyled, overflows, or invisible"
    fix: "Add .css-class with appropriate clamp/color"

outputs:
  board_status_match: "clean | stale | mismatch"
  missing_acceptance: "list of unmet criteria bullets"
  code_gap_location: "file:line references where pieces are missing"
  commit_sha: "commit that implemented task (if applicable)"
  recommended_action: "patch_mc_status | implement_frontend | wire_endpoint | none"

example:
  task_id: "f86b03ee"
  findings:
    backend: "✅ endpoints return npcs_available/available/unavailable split"
    frontend_gap: "❌ personality field not rendered in map.html; portal.html missing TalkTo prompt"
    resolution: "Added template blocks + CSS (44 insertions, 7 deletions)"
    board_contradiction: "✅ None (board status To Do matched code partial)"
  action: "implement_frontend"

notes:
  - Always verify acceptance criteria *explicitly*, not just commit messages
  - Template changes are additive; preserve existing structure
  - When patching board status, include commit SHA and concrete proof in MC update
  - Log contradictions in heartbeat context_summary even if not patching immediately
---

# D20 Board Task Completeness Verification

## Purpose
Systematically verify whether a Mission Control task (To Do or Done) is **genuinely complete** per acceptance criteria, or board-stale/partially-implemented. Catches gaps where backend is complete but frontend rendering is partial, or where commits exist but acceptance criteria aren't fully satisfied.

## When to Use
- Heartbeat cycle task selection for D20 project
- Before marking a task Done, verify it actually meets all acceptance criteria
- When board shows "Done" but recent heartbeats suggest gaps
- When validating that a code change (commit) maps to the intended MC task
- When acceptance requires both backend AND frontend changes

## Methodology

### Step 1: Pull Live Board Context
```
GET http://vps-8432193b:8500/api/context/heartbeat/{config_id}
```
Extract all tasks, filter by status (To Do / In Progress), check `depends_on` satisfaction, and read full `description` and acceptance criteria.

### Step 2: Candidate Task Triage
For each actionable candidate, note:
- Priority (P0/P1/P2/P3)
- Dependencies (all must be Done)
- Task type (Execution vs Spawnable vs Human-coordination — skip non-executable)
- Board ordering (prefer earliest/topmost)

### Step 3: Code-Completeness Audit
For the selected candidate, perform multi-layer verification:

#### 3a. Git History Check
```
git log --oneline --grep "<task_id>"
git show --stat <commit_sha>
```
Confirm commit claims match actual files changed. Does the commit message reference the task ID? Do the modified files align with the described scope?

#### 3b. Backend Implementation Check
- Search for key functions defined in task description
- Check database schema changes (if any)
- Check seed/script additions (movement_rules_json, availability_hours, etc.)
- Verify service functions exist and are connected to endpoints

Example checks:
```bash
grep -rn "def get_available_npcs_at_location" app/
grep -n "movement_rules_json" app/scripts/seed.py
```

#### 3c: API Endpoint Payload Verification
- Inspect endpoint code: does it return the required fields?
- Check both public (no context) and character-scoped paths
- Look for conditional splits (available vs unavailable)

Example:
```python
# map.py GET /api/map/data
if character_id:
    avail_data = get_available_npcs_at_location(loc_id, char_ctx)
    response["npcs_available"] = avail_data["available"]
    response["npcs_unavailable"] = avail_data["unavailable"]
```

#### 3d: Frontend Template Rendering Check
**Most common gap:** Backend returns correct data, but frontend doesn't render it.

- Search HTML templates for data field usage
- Verify CSS classes exist for new styling
- Check that all required acceptance criteria fields appear in the template

Example:
```bash
grep -n "personality" app/static/map.html        # Is it referenced?
grep -n "npc-personality" app/static/map.html    # Is CSS class defined?
```

#### 3e: Test Coverage Check
```bash
ls tests/test_*.py          # Test file exists?
python -m pytest tests/test_<feature>.py -v
```
Note environment-only failures (connection refused) vs actual code failures.

### Step 4: Acceptance Criteria Checklist
Read task acceptance text verbatim. Check each bullet:

- [ ] Specific behavior "(e.g., "talk to Marta" returns Marta")
- [ ] UI elements ("rich NPC cards with portrait, archetype, personality")
- [ ] Data fields present in API responses
- [ ] No regressions ("single-NPC path still works")
- [ ] Tests written and passing

Mark explicit ✅ or ❌ for each. If any ❌, task incomplete.

### Step 5: Board-Status Contradiction Detection
Compare findings:
- **Code Done but board To Do** → MC board stale, should patch
- **Code partial but board Done** → Task mis-marked, log contradiction
- **Code Done and board Done** → Clean, may still verify

Document contradiction in heartbeat `context_summary` with:
- Commit SHAs
- File paths and line numbers
- Specific missing acceptance elements
- Environment constraints (test failures)

## Common Gap Patterns

| Pattern | Symptom | Fix |
|---------|---------|-----|
| Data-return-but-not-rendered | API returns `personality` field, HTML template doesn't display it | Add template interpolation + CSS |
| Single-path working, multi-path stubbed | Deterministic routing committed but UI still shows random selection | Update JS choice logic |
| Service exists but not wired | `get_available_npcs` defined but never called in endpoint | Wire into router |
| CSS missing for new field | Personality text renders unstyled or overflows | Add `.npc-personality` class with clamp |

## Outputs per Verification
- `board_status_match`: `clean` / `stale` / `mismatch`
- `missing_acceptance`: list of unmet criteria
- `code_gap_location`: file + line numbers of missing pieces
- `commit_sha`: if task implemented but not reflected in MC
- `recommended_action`: `patch_mc_status`, `implement_frontend`, `wire_endpoint`, `none`

## Example Application (f86b03ee)
**Task:** Multi-NPC hub cards on map and portal surfaces

**Audit findings:**
- Backend: ✅ Map/portal endpoints return `npcs_available` / `npcs_unavailable` split
- NPC data: ✅ `personality` field present in all NPC summaries
- Map cards: ❌ Personality field not rendered in template
- Portal strip: ❌ Personality field missing; "Talk to X" prompt missing
- CSS: ❌ `.npc-personality` class not defined

**Resolution:** Add template blocks + CSS (additive only). 44 lines changed across 2 files. Task completed.

**Board contradiction found:** 4a292346 code-complete but board still To Do.

## Pitfalls to Avoid
- Don't rely solely on commit messages — verify actual file contents
- Check both character-scoped and public endpoint code paths
- Template changes often need matching CSS; verify both
- Don't forget truncation/length limits (use `substring(0, N)`)
- Keep changes additive — avoid refactoring unrelated code
