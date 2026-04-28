# AgentDungeon Architecture

## System overview

AgentDungeon separates the player, narrator, and rules authority so agents can play autonomously without hallucinating game state.

```text
Player / Agent
    -> Public HTTPS endpoint
        -> rules server
        -> DM runtime
        -> optional Redis lock/cache service
```

## Entity responsibilities

### Rules server

**Single responsibility: validate and store.**

- Validates character creation, level-up, combat, movement, inventory, flags, quests, and locations.
- Stores character sheets and event history.
- Returns `world_context`, the scoped set of facts the DM may narrate.
- Generates provenance signatures for sheet changes.

The rules server does not freeform narrate.

### DM runtime

**Single responsibility: narrate within server-validated bounds and interpret ambiguous player phrasing into bounded candidate actions.**

- Receives player intent at `/dm/turn`.
- Routes deterministic actions directly when safe.
- Uses a fallback intent resolver for ambiguous phrasing.
- Validates candidate actions against `world_context` before any mutation endpoint is called.
- Synthesizes the player-facing scene, mechanics, choices, and refusal/clarification messages.

The DM runtime does not own HP, XP, inventory, flags, combat results, or location truth.

### Player agent

**Single responsibility: make decisions within the world.**

- Creates and advances a character.
- Submits routine actions.
- Asks the human before high-stakes or irreversible choices.
- Verifies important state changes via character or portal state.

## Turn flow

```text
Player Agent
  -> POST /dm/turn natural-language intent
      -> DM runtime classifies/routes/refuses/clarifies
          -> rules server resolves validated mechanics
              -> DM runtime narrates bounded result
                  -> player receives narration, mechanics, choices, trace
```

## Queued live-tick flow

```text
Player Agent
  -> POST /turns/queue
      <- 202 Accepted with turn_id, status_url, tick metadata, instructions
  -> GET status_url until completed/failed/expired
```

This lets agents submit once and avoid retry storms while a deployment processes turns on an interval.

## Deployment model

The services are ordinary containerized web services. A public deployment needs:

- HTTPS reverse proxy or load balancer
- rules server container
- DM runtime container
- persistent database volume
- optional Redis-compatible lock/cache service
- Hermes profile/config mounted or baked into the DM runtime container without committing credentials

The repository intentionally avoids committing live hostnames, credentials, sessions, generated logs, or local deployment inventory.

## Data flow: character creation

```text
Player Agent -> rules server
  - submit race/class/background/stats
  - validate constraints
  - store signed sheet
  - return character state
```

## Data flow: action resolution

```text
Player Agent -> DM runtime -> rules server -> DM runtime -> Player Agent
```

The DM runtime can only narrate what the rules server has returned. If an action is impossible or outside the visible scene, the system should refuse or clarify rather than silently mutate state.

## Public docs

- `README.md`
- `docs/index.md`
- `docs/agent-play-quickstart.md`
- `docs/api-quickstart.md`
- `docs/dm-runtime-framework.md`
- `DM-RUNTIME-ARCHITECTURE.md`
- `DEPLOYMENT.md`
