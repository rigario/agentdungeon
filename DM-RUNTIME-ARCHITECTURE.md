# D20 DM Runtime Architecture

## Purpose

This document defines the target architecture for the D20 DM agent runtime.

The core rule is:
- Server owns rules, state, and authoritative rolls
- DM runtime owns narration, NPC voice, pacing, and player-facing synthesis
- Player/human provides intent and chooses among presented options

This keeps the game deterministic and testable while still feeling like a real Dungeon Master is running the world.

## Current State

What exists today:
- `d20-rules-server` simulates turns, actions, combat, fronts, flags, and atmosphere.
- `d20-dm-runtime` is a separate FastAPI service running in Docker on the deployment environment.
- `POST /dm/turn` accepts player natural language, classifies intent, calls the rules server, and synthesizes the final player-facing DM payload.
- `POST /dm/turn` includes a **DM-agent fallback intent resolver** for flexible/ambiguous input: deterministic routing handles precise actions first; low-confidence/general messages ask the in-container `d20-dm` profile for a bounded JSON decision (`execute`, `clarify`, `refuse`, or `narrate_noop`) before any server mutation.
- `POST /dm/narrate` accepts already-resolved mechanics/world context and narrates without re-entering rules resolution.
- The live DM narrator is a Hermes agent **inside** the `d20-dm-runtime` container:
  - `HERMES_HOME=/root/.hermes`
  - profile: `/root/.hermes/profiles/d20-dm`
  - command: `hermes chat -q ... -Q --profile d20-dm`
- The turn engine returns structured data containing `narrative`, `asks`, `world_context`, `decision_point`, `dice_log`, `decision_log`, and `combat_log`.
- `world_context` is a bounded DM-facing context object with a scope contract.
- Deployment verification is scripted in `scripts/deploy_dm_runtime.sh` and documented in `DEPLOYMENT.md`.

What must remain true:
- The DM uses the isolated Hermes profile mounted inside the `d20-dm-runtime` container. Host-level personal profiles are not part of the runtime contract.
- Repo path `dm-runtime/hermes-home/profiles/d20-dm/` is a Docker build/source artifact only.
- Health is not sufficient proof; actual `/dm/turn` must pass with a non-empty Hermes `session_id`.

## Target System Split

### 1. Rules Server

The existing D20 FastAPI app remains the source of truth.

Responsibilities:
- Character creation and progression validation
- World state and persistence
- Encounter checks
- Combat resolution
- Front progression
- Narrative flags and quest state
- Hidden/authoritative mechanical rolls
- Approval checks
- `world_context` generation

### 2. DM Runtime

A separate FastAPI service plus in-container Hermes agent. It runs as `d20-dm-runtime` on the deployment environment, colocated with the rules server in Docker for isolation.

Responsibilities:
- Accept public player natural language at `/dm/turn`
- Translate player intent into server calls
- Resolve flexible/ambiguous phrasing through the bounded DM-agent fallback resolver when deterministic routing is insufficient
- Route intent to the right server API (`turn`, `actions`, `combat`)
- Accept already-resolved mechanics at `/dm/narrate` for rules-server augmentation without recursion
- Synthesize server output into rich narration through Hermes `d20-dm`
- Voice NPCs using server-provided personality/dialogue/context
- Present options/choices clearly
- Maintain scene/session continuity via Hermes session IDs
- Generate async recaps when turns happen off-session

Runtime invariant:
- Hermes lives only inside the `d20-dm-runtime` container with isolated `HERMES_HOME=/root/.hermes`.

### 3. Player Interface

Any front-end or agent-facing surface.

Responsibilities:
- Accept player messages / choices
- Show narrated responses
- Surface approval moments
- Resume sessions


## Production Deployment Invariant

Live production stack:

```text
Public player / portal
  -> Traefik HTTPS: https://agentdungeon.com
  -> Docker Compose in your deployment directory: /path/to/agentdungeon
     - d20-rules-server  (:8600, authoritative rules/state)
     - d20-dm-runtime    (:8610, DM FastAPI + Hermes agent)
     - d20-redis         (lock/cache support)
```

Canonical deploy/verify command for DM-runtime-only changes:

```bash
cd /path/to/agentdungeon
scripts/deploy_dm_runtime.sh
```

For verification without changing deployment:

```bash
VERIFY_ONLY=1 scripts/deploy_dm_runtime.sh
```

A deploy is only complete when `scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 90` passes after rebuild/recreate.

## Authority Boundaries

### Server must own
- Encounter rolls
- Initiative
- Enemy attacks
- Damage
- XP/loot application
- Quest-state transitions
- Front-state transitions
- Death/defeat conditions
- Any hidden DM check that changes truth

### DM runtime must own
- Descriptive prose
- NPC voice
- Pacing and emphasis
- Scene transitions
- How much mechanical detail to expose in the player-facing response
- Framing player choices

### DM runtime must NOT do
- Direct DB writes
- Freeform world mutation
- Invent off-contract NPCs, locations, items, or outcomes
- Replace server truth with narrative convenience

## DM-Agent Fallback Intent Resolver

The DM runtime contains a bounded fallback resolver for the gap between exact command parsing and real player language. It is documented in detail in `docs/dm-agent-fallback-intent-resolver.md`.

Purpose:
- Enable natural player/player-agent phrasing without requiring exact button labels or route-specific verbs.
- Preserve immersion by letting the DM interpret flexible language the way a human Dungeon Master would.
- Preserve integrity by validating every proposed action/target against `world_context` and existing server affordances before mutation.

Trigger:
- Deterministic routing runs first.
- If the classified intent is `GENERAL`, low-confidence, or otherwise not safely actionable, the runtime asks the in-container Hermes `d20-dm` profile for a strict JSON fallback decision.

Allowed fallback decisions:

| Decision | Meaning | State mutation |
|---|---|---:|
| `execute` | Convert flexible phrasing into a canonical action and target. | Yes, after validation and normal server routing. |
| `clarify` | Ask the player for a narrower or grounded action. | No. |
| `refuse` | Reject impossible/off-world/unsupported action. | No; invalid requests return HTTP 400. |
| `narrate_noop` | Treat as descriptive/already-true local action. | No. |

Integrity rules:
- The resolver must not send raw model text directly to the rules server.
- Returned targets must normalize to current scene affordances: available locations, NPCs, interactables, quests, combat enemies, or other server-provided entities.
- Obvious off-world/anachronistic actions are refused deterministically even if Hermes is unavailable.
- Hermes `session_id` is retained as proof when the fallback path invokes the actual DM agent, even if generated prose is rejected and safe passthrough narration is used.

Verified examples:
- `"wander over to the town square"` → fallback `execute` → canonical `move` to `thornhold` → server persists `location_id=thornhold`.
- `"wander over to the tavern"` while already at the tavern → fallback `narrate_noop` → no mutation.
- `"take out the rocket launcher"` → deterministic/fallback refusal → HTTP 400, no mutation.

## Recommended Interaction Model

## Sync loop (active play)

Use synchronous request/response for moment-to-moment play.

Flow:
1. Player sends message to DM runtime
2. DM runtime classifies intent deterministically
3. If deterministic routing cannot safely act, DM runtime invokes the bounded fallback resolver (`execute` / `clarify` / `refuse` / `narrate_noop`)
4. DM runtime validates any fallback action/target against current scene affordances
5. DM runtime calls one or more server endpoints only after validation
6. DM runtime synthesizes server result into final narrated payload
7. Player chooses next action

This is the loop for:
- travel
- exploration
- NPC interaction
- puzzles
- combat rounds
- immediate post-combat choices

## Async loop (persistent play)

Use asynchronous simulation for off-session advancement.

Flow:
1. Cron/agent submits broad intent to server
2. Server runs turn simulation and stores `turn_results`
3. DM runtime later converts the result into a recap/update
4. Player resumes from the narrated recap

This is the loop for:
- idle adventuring
- background travel
- while-you-were-away updates
- story digests

## Server API Routing Policy

The DM runtime should act as a dispatcher.

### Use `POST /characters/{id}/turn/start`
For broad, high-level intent:
- "explore the forest"
- "travel to the cave"
- "rest and continue"
- "push deeper, but be careful"

Why:
- Turn engine already returns `narrative`, `asks`, `world_context`, and `decision_point`
- Good fit for multi-step simulation and async persistence

### Use `POST /characters/{id}/actions`
For precise explicit actions:
- "talk to Aldric"
- "search the room"
- "solve the altar puzzle with the acorn"
- "cast Fire Bolt"

Why:
- Better for direct interaction and exact verb resolution

### Use `/characters/{id}/combat/*`
For active tactical combat.

Why:
- Combat has its own persistent state machine
- Round-by-round pacing is part of the player experience
- The DM runtime should narrate combat, not flatten it into general turn simulation once combat is active

## Final Player-Facing Payload

The DM runtime should return a structured payload with both narration and actionability.

Suggested shape:

```json
{
  "narration": {
    "scene": "Rich DM prose describing what just happened.",
    "npc_lines": [
      {"speaker": "Aldric", "text": "..."}
    ],
    "tone": "ominous"
  },
  "mechanics": {
    "what_happened": [
      "You moved from Thornhold to Forest Edge",
      "Encounter triggered: Goblin Scouts",
      "You took 4 damage"
    ],
    "hp": {"current": 8, "max": 12},
    "xp": {"current": 325, "next_level_at": 900},
    "location": "forest-edge"
  },
  "choices": [
    {"id": "push_on", "label": "Press deeper into the woods"},
    {"id": "rest", "label": "Make camp and recover"},
    {"id": "return", "label": "Return to Thornhold"}
  ],
  "server_trace": {
    "turn_id": "abc123",
    "decision_point": {"type": "danger"},
    "available_actions": ["move", "attack", "rest", "explore", "interact", "puzzle", "cast"]
  }
}
```

This shape keeps:
- good storytelling
- player trust via visible mechanics
- clean structured options for agents/UIs
- strong debugging hooks

## Session Memory

The DM runtime should own lightweight session memory that is separate from game truth.

Suggested session state:
- session_id
- character_id
- latest_turn_id
- current_scene_summary
- last_location
- last_speaking_npc
- open_choices
- unresolved tensions / scene focus
- narration style/tone for current scene

This memory should NOT become authoritative game state.
It is only there to preserve continuity and improve the player-facing DM experience.

## Hermes / Kimi Runtime Recommendation

Recommended setup:
- Run a dedicated Hermes profile for the DM runtime
- Pin model to Kimi 2.5
- Constrain the profile prompt so it:
  - never invents rules outcomes
  - never mutates truth directly
  - only narrates from server-returned data
  - uses `world_context` as hard scope

Why Kimi here:
- strongest public deployment narrative value
- visible Kimi usage in the live demo
- model is used exactly where synthesis matters most
- mechanical correctness remains server-side

## Staged Build Plan

### Stage 1 — Thin DM Wrapper
- Input: player message
- Output: narration + choices
- Classify intent and route to existing server endpoints
- Minimal session memory
- Enough for public deployment

### Stage 2 — Scene Continuity Layer
- Better NPC continuity
- Better transitions between turns
- Stronger recap/resume behavior
- Explicit scene memory store

### Stage 3 — Multi-step DM Orchestration
- Support one player message triggering multiple server calls when appropriate
- Better handling of mixed intent (move + interact + react)
- Cleaner sync/async convergence

## Current Gap Summary

Where we are:
- DM-compatible server payloads exist
- world_context and asks exist
- atmosphere/fronts/dialogue filtering exist
- no standalone DM runtime exists

Where we need to be:
- dedicated DM runtime process/service
- intent router over turn/actions/combat
- final narrated payload contract
- scene/session memory
- async recap/resume flow
- Kimi-powered Hermes profile for storytelling

## Suggested Task Breakdown

1. Define DM runtime contract and payload schema
2. Create Hermes DM profile pinned to Kimi 2.5
3. Build DM runtime wrapper service
4. Implement intent routing across turn/actions/combat
5. Add session memory + async recap/resume flow
6. Add end-to-end demo path and integration tests

## Non-Negotiable Invariant

The DM runtime is not the game engine.

It is the narrative interpreter sitting on top of an authoritative rules server.
