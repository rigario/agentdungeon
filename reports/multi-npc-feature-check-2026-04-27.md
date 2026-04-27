# Multi-NPC Feature Check — 2026-04-27

## Board status
Live Mission Control pull: 11 relevant Multi-NPC / hub tasks found, all `Done`.

Task IDs:
- b99be563 — expand hub rosters — Done
- 64ce5164 — production schema drift — Done
- 4a292346 — availability/movement rules — Done
- 8084708d — deterministic DM context/interact routing — Done
- c47ee638 — live deploy verification — Done
- 9826f50c — post-character-flow audit gate — Done
- a98bc0a9 — real handler/endpoints regression tests — Done
- 6cb970ec — absurd/nonsensical target validation — Done
- c19666d4 — authored hub content pass — Done
- fbe3830a — hub rumor/faction reaction layer — Done
- f86b03ee — hub-level NPC cards/map/portal surfaces — Done

## Live production verification
- `GET https://d20.holocronlabs.ai/health` -> 200
- `GET https://d20.holocronlabs.ai/api/map/data` -> 200
- Map data: 11 locations; 7 locations have >=2 NPCs.
- Counts: Rusty Tankard 3, Thornhold 4, South Road 2, Crossroads 2, Forest Edge 2, Greypeak Pass 3, Cave Depths 2.
- `POST /characters` succeeded with test character `alpha-multinpc-check-1777264895-817eed`.
- `GET /characters/{id}` succeeded.
- `POST /actions` with no target at Rusty Tankard returned explicit NPC-selection choices for Aldric, Bohdan, and Tally.
- `POST /actions` with target `Aldric the Innkeeper` succeeded and returned dialogue.

## Local tests
- `python3 -m pytest tests/test_multi_npc_determinism.py tests/test_hub_rumors.py -q` -> 6 passed, 5 skipped.
- Broader suite `tests/test_multi_npc_determinism.py tests/test_hub_rumors.py tests/test_hub_rumors_integration.py tests/test_npc_availability.py` -> 17 passed, 7 skipped, 2 failed.
- The 2 failures are movement-trigger tests in `tests/test_npc_availability.py` when run as part of the broader suite; the same two tests pass when run isolated.

## Caveats / follow-ups
1. `GET /characters` still returns 500 even though `POST /characters` and `GET /characters/{id}` work.
2. `tests/test_npc_availability.py` has state/order-dependent failures in the broader multi-NPC suite. Likely test isolation issue around `get_db()` / persistent DB state rather than a direct live feature failure, but it should be fixed before calling the suite fully green.
3. Unknown target `nobody-real` in a multi-NPC location returns the NPC chooser. This may be acceptable for ambiguous unknown targets, while absurd target validation has separate task coverage, but it is worth checking whether target strings with hyphens should refuse instead of prompting.

## Verdict
Core Multi-NPC feature is live and working for roster density, selection routing, explicit NPC interaction, and hub rumor/local deterministic tests. Remaining work is hardening/test cleanup, not core implementation.
