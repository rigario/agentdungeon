# D20 Playtest Issues Log

**Last Reviewed:** 2026-04-23 09:50 SGT (Alpha — all P1/P2 issues fixed and deployed)

**Open Issues:** 0 | **Fixed Issues:** 5

---

## Fixed Issues

### ISSUE-001: DM runtime root endpoint returns HTML instead of JSON (test mismatch)
**Fixed:** 2026-04-23 — Smoke test updated to check `/dm/health` instead of `/`
**Fix:** `tests/test_smoke.py` — `test_dm_runtime_health` now validates `/dm/health` endpoint
**Verified:** 16/16 smoke tests pass on VPS

### ISSUE-002: PLAYTEST-ISSUES.md file was missing from repository
**Fixed:** 2026-04-23 — File created and committed to git (commit 9036249)
**Fix:** Added both PLAYTEST-ISSUES.md and PLAYTEST-GUIDE.md to repo

### ISSUE-003: NPC interact targeting broken — target parameter ignored, random NPC selected
**Fixed:** 2026-04-23 — NPC query now filters by `current_location_id` in addition to biome
**Fix:** `app/routers/actions.py` line 1414 — changed query from `WHERE biome = ?` to `WHERE biome = ? AND current_location_id = ?`
**Root Cause:** Biome-only query returned all NPCs sharing the biome regardless of specific location
**Verified:** Interact with "Sister Drenna" at south-road now correctly returns Drenna dialogue

### ISSUE-004: Character current_location_id not updated after move action
**Fixed:** 2026-04-23 — Move handler now uses resolved location ID from `_resolve_move` instead of raw `body.target`
**Fix:** `app/routers/actions.py` line 748 — changed `(body.target, ...)` to `(result['new_location'], ...)`
**Root Cause:** Raw user input (e.g., "south road") was stored instead of canonical location ID ("south-road"), causing downstream lookup failures
**Verified:** Character location persists correctly after move; GET /characters returns updated location_id

### ISSUE-005: Absurd/impossible actions trigger travel instead of refusal
**Fixed:** 2026-04-23 — Added absurd action guardrail in intent router + refusal narration in synthesis
**Fix:** `dm-runtime/app/services/intent_router.py` — `_ABSURD_PATTERNS` regex list + detection block before default return
**Fix:** `dm-runtime/app/services/synthesis.py` — `_build_absurd_refusal()` generates refusal narration
**Verified:** "I swallow the statue whole" returns refusal narration, no location change

---

## Deployment

**Commit:** 9036249 on main branch
**VPS:** Deployed 2026-04-23 ~09:45 SGT — both containers rebuilt and recreated
**Smoke tests:** 16/16 PASS on VPS

---

## Template for New Issues

> **Category:** Combat | Narrative | Technical | UX
> **Reproduces:** YES / NO / PARTIAL
> 
> **Steps:** 1. ... 2. ...
> **Expected:** ...
> **Actual:** ...
> 
> **Evidence:**
> - Endpoint: ...
> - Status: ...
> - Character ID: ...
> - Timestamp: ...
