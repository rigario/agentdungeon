

### Alpha Verifier Note — 2026-04-24T16:11:19.610580 (heartbeat 309)

Task f829f9d4 (Internal playtest gate) — status **In Progress** confirmed correct.

**Code-level findings (verified at HEAD ):**
- All 6 DM agent flow contract tests pass
- dm_sessions infrastructure present and used
- build_world_context compiles full context pre-turn
- DM proxy uses /dm/narrate (safe one-way flow)
- X-DM-Runtime recursion guard active on /actions
- _extract_trace restored in synthesis (combat_log populated)

**Live VPS state (from PLAYTEST-ISSUES.md 2026-04-24 07:55):**
- Smoke test: 16/19 PASS, 3 P1 regressions active
  - test_move_updates_location_id → location_id=None post-move (ISSUE-007)
  - test_explore_turn → /dm/turn 500 after 11.8s (ISSUE-013)
  - test_move_turn → /dm/turn ReadTimeout >12s (ISSUE-013)
- /dm/health reports: mode=direct, runtime_ready=false
- Environment: DM_HERMES_MODE=direct (should be hermes), Hermes binary inaccessible
- Profile: kimi-k2.5 + api.kimi.com/coding (stale)

**Root cause:** VPS deployment stale — container at pre-fix commit (9036249), HEAD is e9959aa (8+ commits behind). Environment misconfiguration (DM_HERMES_MODE, profile base_url).

**Action required before f829f9d4 can close:**
1. Rigario rebuilds dm-runtime container from latest `main`
2. Set DM_HERMES_MODE=hermes in .env; ensure /usr/local/bin/hermes exists in container
3. Update d20-dm profile to kimi-for-coding model + /coding/v1 base URL
4. Verify /dm/health returns `runtime_ready=true`
5. Rerun smoke suite; if 6/6 PASS, execute full Scenario A walkthrough

**Impact:** 7 downstream tasks blocked until this gate passes.

