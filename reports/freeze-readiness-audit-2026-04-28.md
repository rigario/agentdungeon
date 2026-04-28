# D20 Freeze / Hackathon Readiness Audit — 2026-04-28T03:00:03Z

## Bottom line

Not freeze-ready yet. The public rules server is up and the basic character/action path works, but the DM narrative loop is not reliable enough for a hackathon submission: `/dm/turn` can lose the live scene context, returns an empty `choices` array on planner-clarify, and reports `mechanics.hp=0` / `location=unknown` for a fresh healthy character. The board was mostly directionally right, but too optimistic on the narrative-driver work and too quiet on two regressions: `GET /characters` returns 500, and the local test suite has collection/plugin failures.

## Live board snapshot

Source: `GET http://vps-8432193b:8500/api/context/project/rigario-d20-agent-rpg`

- Total tasks: 191
- Status counts: Done 184, To Do 4, In Progress 2, Blocked 1
- Open tasks before reconciliation:
  - `b353721b` To Do P1 — Freeze hardening: encounter balance/safe validation route
  - `bce39ecd` To Do P1 — Freeze hardening: full playthrough harness recovery
  - `0c056bba` In Progress P0 — DM choices from scene affordances
  - `796fc9c2` In Progress P0 — DM narrative driver / LLM affordance planner
  - `b1939d5c` To Do P1 — Social driver: hub rumors / affinity dialogue hooks
  - `f849892f` Blocked P0 — Certification matrix
  - `53871fd5` To Do P1 — First invited external playtest

## Verified actual state

### Production checks

- `GET https://d20.holocronlabs.ai/health` → 200, `db_connected=true`.
- `GET https://d20.holocronlabs.ai/openapi.json` → 200.
- `GET https://d20.holocronlabs.ai/api/map/data` → 200; 10 locations, 7 locations with >=2 NPCs.
- `GET https://d20.holocronlabs.ai/characters` → 500 Internal Server Error.
- `POST https://d20.holocronlabs.ai/characters` → 201; fresh character created.
- `GET /characters/{id}/scene-context` → 200; scene context has 7 allowed actions, 3 NPCs, 1 exit.
- `POST /actions` look → 200; returns scene-affordance choices including movement, look/explore/rest, and NPC inspect choices.
- `POST /characters/{id}/actions` interact Aldric → 200; direct action path works.
- `POST /characters/{id}/turn/start` → 200; creates waiting turn.
- `POST /dm/intent/analyze` → 200.
- `POST /dm/turn` with fresh tavern character + “talk to Aldric” → 200 but wrong behavior: says Aldric is not here, lists NPCs from another location, returns `choices: []`, `mechanics.hp.current=0`, `mechanics.location=unknown`.

### Local code / tests

- Git working tree has significant uncommitted work and untracked scripts/tests.
- Recent commits include `009acc6` and `9b12bf3` for scene context fallback and choice generation.
- `dm-runtime/app/services/narrative_planner.py` exists, but has zero LLM calls; it is heuristic/keyword-based.
- `app/services/hub_rumors.py` and `app/services/scene_context.py` are wired, but no standalone social-driver/dialogue-hook orchestrator exists.
- `scripts/full_playthrough_with_gates.py` exists (518 lines), but contains no explicit combat/death/recovery state machine.
- `python3 -m pytest dm-runtime/tests/test_extract_choices_affordances.py dm-runtime/tests/test_narrative_planner.py -q` → 34 passed, 3 failed due missing async pytest plugin support.
- `python3 -m pytest dm-runtime/tests/test_intent_router_freshen.py -q` → 7 failed due missing async pytest plugin support.
- `python3 -m pytest tests/test_scene_context.py -q` → collection SyntaxError at line 39 due unescaped quotes in SQL string.

## Task-by-task status verdict

| Task | Board before | Reality verdict | Recommended / applied board action |
|---|---:|---|---|
| `0c056bba` DM choices from scene affordances | In Progress | Correct status. Code exists and `/actions` choices work; `/dm/turn` still fails acceptance with stale scene context + empty choices. | Keep In Progress; update description with live failure proof. |
| `796fc9c2` narrative-driver affordance planner | In Progress | Partial. Planner exists before mutation but is not LLM-based. | Keep In Progress; update description to clarify heuristic vs LLM gap. |
| `b1939d5c` social driver | To Do | Partial lower-layer hub rumor work exists; actual social driver/dialogue hooks absent and blocked by `0c056bba`. | Move to Blocked; update description. |
| `f849892f` certification matrix | Blocked | Correct. Cannot certify while P0 narrative-driver path is unstable. | Keep Blocked; update description. |
| `b353721b` safe validation route / encounter balance | To Do | Correct. Not implemented; still needed for predictable demo route. | Keep To Do; update description. |
| `bce39ecd` full playthrough harness recovery | To Do | Correct. Harness exists but lacks recovery for combat/death/movement failure. | Keep To Do; update description. |
| `53871fd5` invited external playtest | To Do | Not actionable. Human/external coordination plus freeze blockers. | Move to Blocked; update description. |

## New tasks needed

1. P0 production regression: `GET /characters` returns 500; smoke gate is not green.
2. P1 local verification gap: async test support + `tests/test_scene_context.py` SyntaxError prevent reliable verifier heartbeats.

## Freeze/hackathon critical path

1. Fix `/dm/turn` scene-context drift and empty choices for planner-clarify. This is the demo-killer.
2. Fix production `GET /characters` 500 or explicitly remove it from smoke gate if list endpoint is nonessential; current state contradicts prior smoke-gate Done claims.
3. Harden the playthrough harness to recover from combat/death/failed movement and use a safe validation route.
4. Repair local test collection/async environment so verifier heartbeats can give reliable signal.
5. Only then run certification matrix + invited external playtest + submission video.

## Non-obvious dot connections / edge hypotheses

1. `/actions` has the correct scene-affordance path, while `/dm/turn` does not. The fastest fix is likely not new planner intelligence; it is reusing the same `scene-context` payload/hydration path already proven by `/actions`.
2. `POST /characters` works while `GET /characters` fails, so the regression is probably in list serialization/query shape rather than core character persistence.
3. The DM response listing Ser Maren/Marta/Brother Ferron/Bobby while the fresh character is at Rusty Tankard suggests character/session mismatch or stale latest-turn world context beating fresh scene context.
4. `mechanics.hp=0` / `location=unknown` in `/dm/turn` is a trust-killer even if narration is acceptable; it implies synthesis fallback defaults are leaking to the user surface.
5. Async pytest failures may be hiding real regressions. The missing plugin makes the test suite look red for environment reasons, but it also means the exact DM-runtime integration tests that should catch this are not providing signal.

## Management / project subtext

The board is 96% Done by count, but the remaining 4% is concentrated in demo-critical narrative reliability. The risk is not feature volume; it is confidence. For the hackathon, a short guided route with believable choices beats broad system completeness. Freeze should mean “one reproducible story path works every time,” not “all systems theoretically exist.”

## Proof references

- Board snapshot: `/tmp/d20_board_snapshot.json`
- Report: `/home/rigario/Projects/rigario-d20/reports/freeze-readiness-audit-2026-04-28.md`
- Sub-agents: local repo audit, production audit, MC API contract audit.
- Commands/probes run by Alpha: git status/log; focused pytest; live `urllib` probes against `/health`, `/openapi.json`, `/characters`, `/api/map/data`, `/characters/{id}/scene-context`, `/actions`, `/dm/turn`.
