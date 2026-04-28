# DM-Agent Fallback Intent Resolver

**Status:** Implemented and deployed 2026-04-28  
**Primary code:** `dm-runtime/app/services/intent_fallback.py`  
**Runtime path:** `POST /dm/turn` inside `d20-dm-runtime`  
**Design goal:** Enable full player flexibility while preserving game integrity, immersion, and server authority.

## Why This Exists

The D20 product experience is not "choose only from exact buttons." A player or player-agent should be able to say natural things like:

- "wander over to the town square"
- "make my way toward the inn"
- "ask the guard what happened here"
- "poke around for anything useful"

Before this feature, the deterministic intent router handled exact or near-exact verbs well, but flexible language could degrade into generic turn simulation, wrong movement, or a misleading no-op. The fallback intent resolver adds a bounded DM interpretation layer for those ambiguous cases.

The core product invariant remains unchanged:

> The DM may interpret player intent, but the server remains the referee. The DM can propose an action; only validated scene affordances and server endpoints can mutate state.

## High-Level Flow

```text
Player message
  -> deterministic NarrativePlanner precheck
  -> deterministic classify_intent()
  -> if intent is precise/high-confidence:
       route normally
  -> if intent is GENERAL / low-confidence:
       call DM-agent fallback resolver
       validate returned action/target against current scene affordances
       execute, clarify, refuse, or narrate no-op
  -> approval gate / server endpoint
  -> synthesis / narration
```

This is not a freeform LLM mutation path. It is a constrained interpreter between player language and canonical server actions.

## Resolver Contract

The resolver asks the in-container `d20-dm` Hermes profile for strict JSON:

```json
{
  "decision": "execute|clarify|refuse|narrate_noop",
  "action_type": "move|interact|explore|rest|attack|cast|quest|puzzle|look|null",
  "target": "known target id/name or null",
  "confidence": 0.0,
  "reason": "brief explanation",
  "clarifying_question": "question when decision=clarify",
  "narration_hint": "safe narration hint when decision=narrate_noop"
}
```

Allowed decisions:

| Decision | Meaning | Mutates state? |
|---|---|---:|
| `execute` | DM inferred a valid canonical action and target from flexible language. | Yes, after validation and normal server routing. |
| `clarify` | The player intent is ambiguous or underspecified. | No. |
| `refuse` | The requested action is impossible, off-world, or unsupported. | No; returns HTTP 400 for invalid actions. |
| `narrate_noop` | The action is descriptive or already true, e.g. walking to the tavern while already there. | No. |

## Integrity Boundaries

The resolver must validate model output before mutation:

1. **No invented targets.** A returned target must match current `world_context` affordances: locations/connections, NPCs, interactables, quests, combat enemies, or other server-provided entities.
2. **No invented actions.** `action_type` must map to supported canonical server actions.
3. **No off-world/anachronistic actions.** Obvious impossible examples are refused deterministically before relying on the model.
4. **No database writes.** The DM runtime does not write directly to the database. It only calls existing rules-server endpoints.
5. **No replacement of server truth.** Server response remains authoritative for mechanics, HP, loot, location, combat, flags, and progression.

## Deterministic Off-World Guard

Some invalid inputs should never depend on model judgment. The fallback layer hard-refuses obvious anachronistic or impossible requests such as:

- `rocket launcher`
- `machine gun`
- `grenade`
- `smartphone`
- `google the map`
- `laser`
- `robot`
- `tank`
- `helicopter`

Expected behavior:

```text
POST /dm/turn "take out the rocket launcher"
-> HTTP 400
-> detail: "That does not exist in this world..."
-> no rules-server mutation
```

## Immersion Behavior

The resolver should preserve the feeling of a real Dungeon Master:

- If the player says a reasonable thing in unusual wording, resolve it naturally.
- If the player asks for an impossible thing, refuse in-world or ask for a grounded alternative.
- If the player describes movement within the current scene, prefer `narrate_noop` or local description over false travel.
- If the player intent is ambiguous, ask a clarifying question rather than guessing a mutation.

Example verified behavior:

```text
Input: "wander over to the town square"
DM fallback: execute move target=thornhold
Server: POST /characters/{id}/actions
Result: location persisted as thornhold
```

Example no-op behavior:

```text
Input: "wander over to the tavern" while already at The Rusty Tankard
DM fallback: narrate_noop
Result: no mutation; player gets a local description/continuation
```

## Observability and Debugging

Fallback decisions are surfaced in `server_trace`:

```json
{
  "server_endpoint_called": "actions",
  "intent_used": {
    "type": "move",
    "target": "thornhold",
    "details": {
      "_dm_fallback": true,
      "_dm_fallback_reason": "Player wants to leave the inn and go to town square...",
      "_dm_fallback_confidence": 0.9
    }
  }
}
```

No-op/refusal decisions may appear as trace entries such as:

```text
server_endpoint_called: dm-fallback-narrate_noop
combat_log: {type: dm_fallback, decision: narrate_noop, reason: ...}
```

Hermes session IDs must be preserved when the actual DM agent runs, even if prose is rejected by scope validation and synthesis falls back to safe server passthrough. This provides proof that the DM agent path was exercised without allowing off-scope narration.

## Files and Responsibilities

| File | Responsibility |
|---|---|
| `dm-runtime/app/services/intent_fallback.py` | LLM fallback resolver, strict JSON parsing, affordance validation, deterministic off-world guard. |
| `dm-runtime/app/services/intent_router.py` | Calls fallback resolver for GENERAL / low-confidence messages and constructs canonical `Intent` / `RouterResult`. |
| `dm-runtime/app/services/narrator.py` | Preserves Hermes session proof when scope validation rejects unsafe/off-scope prose. |
| `dm-runtime/app/services/synthesis.py` | Carries fallback-safe Hermes `session_id` through passthrough responses. |
| `dm-runtime/tests/test_intent_fallback.py` | Resolver unit coverage. |
| `dm-runtime/tests/test_intent_router_fallback.py` | Router integration coverage. |
| `tests/test_dm_runtime_synthesis.py` | Session preservation and synthesis regression coverage. |

## Required Verification

Before claiming this feature works, verify all of the following:

1. Local tests:
   ```bash
   cd /home/rigario/Projects/rigario-d20
   python3 -m py_compile dm-runtime/app/services/intent_fallback.py dm-runtime/app/services/intent_router.py dm-runtime/app/services/narrator.py dm-runtime/app/services/synthesis.py
   cd dm-runtime && python3 -m pytest tests/test_intent_fallback.py tests/test_intent_router_fallback.py tests/test_target_normalization.py -q --tb=short
   cd .. && python3 -m pytest tests/test_dm_runtime_synthesis.py tests/test_dm_agent_flow_contract.py tests/test_intent_router.py -q --tb=short
   ```

2. DM runtime deployment:
   ```bash
   cd /home/rigario/Projects/rigario-d20
   scripts/deploy_dm_runtime.sh
   ```

3. Live valid-flexible action:
   - Create fresh character.
   - `POST /dm/turn` with `"wander over to the town square"`.
   - Expect HTTP 200.
   - Expect `_dm_fallback: true` in `server_trace.intent_used.details`.
   - Expect canonical action execution and persisted location.

4. Live invalid/off-world action:
   - `POST /dm/turn` with `"take out the rocket launcher"`.
   - Expect HTTP 400.
   - Expect no state mutation.

5. Production smoke:
   ```bash
   SMOKE_RULES_URL=https://agentdungeon.com \
   SMOKE_DM_URL=https://agentdungeon.com \
   python3 -m pytest tests/test_smoke.py -q --tb=short
   ```

## Known Edge Cases

- The fallback resolver depends on Hermes/Kimi for genuinely ambiguous natural-language interpretation. Deterministic off-world refusal remains available even if the model is unavailable.
- A DNS or upstream rules-server issue can still produce transient 502s after a valid fallback decision. Distinguish interpretation correctness from infrastructure failure by checking `/health`, `/dm/health`, and direct rules-server endpoint behavior.
- If the DM proposes a plausible target alias, the resolver must normalize it to a canonical scene target before mutation. Raw model text should not be sent to the rules server as-is.

## Strategic Significance

This feature is the hinge between a button-driven RPG and a genuinely agent-native RPG:

- **Player flexibility:** players and agents can speak naturally.
- **Immersion:** invalid actions are handled like a DM would handle them, not as random route failures.
- **Integrity:** every mutation still passes through server-side rule validation.
- **Debuggability:** fallback decisions are visible in traces and testable independently.

The moat is not just that the game has an LLM narrator. The moat is that natural-language freedom is bounded by a deterministic game-state contract.
