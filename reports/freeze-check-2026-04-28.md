# D20 Freeze Check — 2026-04-28T14:00:55Z

## Bottom-line verdict

**Near-freeze / demo-freeze ready for a controlled hackathon path, but not final submission-frozen until repo hygiene + final video/script packaging are done.**

The actual deployed product is green on core production gates:
- `/health` 200, database connected.
- `/dm/health` healthy, Hermes narrator enabled, runtime_ready=true.
- `scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 120` passed.
- `scripts/production_smoke_gate.py` passed 10/10.
- `tests/test_smoke.py` passed 20/20 when run with production env vars.
- Live map has 10 locations, 10/10 with `connected_to`, 7 locations with >=2 NPCs.
- `GET /characters` now returns 200 (previous 500 regression no longer present).

The only true D20 project-board open items from `GET /api/context/project/rigario-d20-agent-rpg` are:
- `b353721b` To Do P1 — encounter balance / safe validation route for short playthrough.
- `53871fd5` Blocked P1 — first invited external playtest.

## What still needs pushing before hackathon submission

### Must push before submission freeze
1. **Repo hygiene / final commit bundle** — production code and tests are still dirty locally, including new untracked `dm-runtime/app/services/intent_fallback.py`. This is the biggest operational risk: production appears live, but source control is not clean.
2. **Demo route lock** — pick a deterministic, short guided route that avoids the active-combat trap seen in the full playthrough harness after the wolf encounter.
3. **Submission package** — final video, README/demo instructions, links, and proof artifacts.

### Should not block controlled freeze
1. `b353721b` encounter balance/safe route — this is real but game-design/harness hardening, not a core infrastructure blocker. It should be treated as the final demo-route tuning task.
2. `53871fd5` external invited playtest — correctly blocked until the demo route is locked and the submission narrative is packaged.
3. Moonshots such as multimodal puzzles — explicitly post-freeze.

## Live verification results

| Gate | Result | Evidence |
|---|---:|---|
| Rules health | PASS | `GET https://agentdungeon.com/health` -> 200, `db_connected=true` |
| DM health | PASS | `/dm/health` -> `status=healthy`, `mode=hermes`, `runtime_ready=true` |
| Actual DM turn | PASS | `validate_actual_dm_agent_turn.py`: created `actualdmnossry-efd905`, `/dm/turn` 200 in 14.84s, session `20260428_135411_59d1f8` |
| Production smoke gate | PASS | 10/10 passed |
| Pytest smoke against production | PASS | `SMOKE_RULES_URL=... SMOKE_DM_URL=... python3 -m pytest tests/test_smoke.py -q` -> 20 passed |
| Focused DM fallback tests | PASS | `dm-runtime` focused tests -> 30 passed |
| Broad selected local tests | MIXED but explained | 131 passed / 4 failed when env vars omitted; rerun with prod env yielded 20/20 smoke pass |
| Full playthrough harness | PARTIAL | Script completed, 9 DM turns logged, but active combat blocks later Drenna/Kol phases; this supports keeping `b353721b` open |

## Board truth reconciliation

Project context board: 194 tasks = 192 Done, 1 To Do, 1 Blocked.

| Task | Board status | Reality | Action |
|---|---:|---|---|
| `b353721b` Freeze hardening: encounter balance/safe validation route | To Do | Correct. Core app green, but full playthrough can enter active combat and block later story phases. | Keep open; focus next on deterministic demo route / safe validation route. |
| `53871fd5` First invited external playtest | Blocked | Correct. External/human coordination plus should wait until route/video package is locked. | Keep blocked. |

## Management / project subtext

The project is no longer in “build major missing systems” mode. The board count and live gates both say the same thing: **we are at freeze-adjacent polish/packaging**. The danger is not that the product cannot run; it can. The danger is freezing with an unclean repo and a broad playthrough path that wanders into combat-state friction. For hackathon odds, the winning move is not more systems — it is a controlled trailer path.

## Non-obvious dot connections / edge hypotheses

1. The live product is healthier than the older freeze audit: `GET /characters` moved from 500 to 200 and smoke is green, so prior P0 infrastructure blockers are resolved.
2. The remaining `b353721b` task is less about code existence and more about demo-route authorship: combat is working, but it can trap a narrative walkthrough if not intentionally bounded.
3. The full playthrough script’s active-combat stall is useful signal: it identifies where the submission video should either cut away, resolve combat explicitly, or avoid that branch.
4. Dirty source control is now a higher risk than endpoint behavior: if the VPS is live from uncommitted/untracked code, a rebuild or handoff could silently drop freeze-critical behavior.
5. The board has cross-project spillover in `/api/tasks`, but project-scoped context correctly reduces to only two D20 open items; use project context for D20 freeze truth.

## Proof references

- Live board: `GET http://vps-8432193b:8500/api/context/project/rigario-d20-agent-rpg` -> 194 tasks, 192 Done / 1 To Do / 1 Blocked.
- Health: `curl https://agentdungeon.com/health`; `curl https://agentdungeon.com/dm/health`.
- DM validator: `python3 scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 120`.
- Smoke gate: `SMOKE_RULES_URL=https://agentdungeon.com SMOKE_DM_URL=https://agentdungeon.com SMOKE_CLEANUP=1 python3 scripts/production_smoke_gate.py`.
- Smoke pytest: `SMOKE_RULES_URL=https://agentdungeon.com SMOKE_DM_URL=https://agentdungeon.com python3 -m pytest tests/test_smoke.py -q`.
- Full playthrough harness: `D20_RULES_URL=https://agentdungeon.com DM_URL=https://agentdungeon.com PLAYTEST_RUNS_DIR=/tmp/d20-freeze-playtest-runs python3 scripts/full_playthrough_with_gates.py`.
- Subagents: live readiness gate audit and repo-state audit; board audit subagent timed out, so I used direct project-context API results instead.
