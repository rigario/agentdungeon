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
- The FastAPI server simulates turns, actions, combat, fronts, flags, and atmosphere
- The turn engine returns a structured payload containing:
  - narrative
  - asks
  - world_context
  - decision_point
  - dice_log
  - decision_log
  - combat_log
- `world_context` is already a bounded DM-facing context object with a scope contract
- `narrative_introspect` endpoints provide debugging/audit views of story state

What does NOT exist yet:
- A standalone DM runtime process or service
- A player-facing DM session loop
- A session-memory layer for scenes, NPC continuity, and async recap/resume
- A Hermes/Kimi-powered storyteller wrapper that consumes server payloads and returns final narration + choices

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

A separate Hermes-based runtime, ideally pinned to Kimi 2.5 for hackathon/demo value.

Responsibilities:
- Translate player intent into server calls
- Route intent to the right server API (`turn`, `actions`, `combat`)
- Synthesize server output into rich narration
- Voice NPCs using server-provided personality/dialogue/context
- Present options/choices clearly
- Maintain scene/session continuity
- Generate async recaps when turns happen off-session

### 3. Player Interface

Any front-end or agent-facing surface.

Responsibilities:
- Accept player messages / choices
- Show narrated responses
- Surface approval moments
- Resume sessions

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

## Recommended Interaction Model

## Sync loop (active play)

Use synchronous request/response for moment-to-moment play.

Flow:
1. Player sends message to DM runtime
2. DM runtime classifies intent
3. DM runtime calls one or more server endpoints
4. DM runtime synthesizes server result into final narrated payload
5. Player chooses next action

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
- strongest hackathon narrative value
- visible Kimi usage in the live demo
- model is used exactly where synthesis matters most
- mechanical correctness remains server-side

## Staged Build Plan

### Stage 1 — Thin DM Wrapper
- Input: player message
- Output: narration + choices
- Classify intent and route to existing server endpoints
- Minimal session memory
- Enough for hackathon demo

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
