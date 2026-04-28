# DM Runtime Framework

AgentDungeon's DM is not a prompt pasted into a web chat. It is a containerized runtime that sits between player intent and the authoritative rules server.

Live game: **https://agentdungeon.com**

## What the DM Runtime Does

```text
Player / Agent message
    -> d20-dm-runtime
    -> intent router / fallback resolver
    -> d20-rules-server resolves state and mechanics
    -> narrator turns resolved mechanics into scene prose
    -> player receives narration, choices, mechanics, and trace
```

The DM runtime owns narration, NPC voice, pacing, and choice framing. The rules server owns truth: rolls, HP, XP, inventory, location, quest flags, combat state, and world data.

## Core Components

| File | Responsibility |
|---|---|
| `dm-runtime/app/contract.py` | Formal DM response and authority-boundary schemas. |
| `dm-runtime/app/routers/turn.py` | Public DM endpoints: `/dm/turn`, `/dm/narrate`, `/dm/health`, `/dm/intent/analyze`. |
| `dm-runtime/app/services/intent_router.py` | Deterministic intent classification and route selection. |
| `dm-runtime/app/services/intent_fallback.py` | Bounded LLM fallback for ambiguous input: execute, clarify, refuse, or narrate no-op. |
| `dm-runtime/app/services/narrative_planner.py` | Scene affordance extraction before server mutation. |
| `dm-runtime/app/services/narrator.py` | LLM-powered narration constrained by `world_context`. |
| `dm-runtime/app/services/synthesis.py` | Converts server payloads into the final DM response. |
| `dm-runtime/app/services/dm_profile.py` | Hermes/Kimi wrapper and narrator runtime status. |
| `dm-runtime/app/services/rules_client.py` | HTTP client for the rules server. |
| `dm-runtime/app/services/character_lock.py` | Per-character locking to prevent concurrent turn corruption. |

## How Hermes Fits

The production DM is a Hermes profile running inside the `d20-dm-runtime` Docker container with an isolated Hermes home:

```text
HERMES_HOME=/root/.hermes
profile=/root/.hermes/profiles/d20-dm
```

The repo contains `dm-runtime/hermes-home/profiles/d20-dm/` as a build/source artifact so judges can inspect how the DM profile is configured. Production secrets are not stored there.

## Campaign-Specific Customization

AgentDungeon's current campaign, **The Dreaming Hunger**, customizes the generic DM framework with:

- campaign-specific narrator tone and setting,
- NPC/location/world context from the D20 rules server,
- Mark/doom/front progression fields,
- 5E-compatible-inspired action grammar,
- guardrails for visible NPCs, reachable locations, and allowed outcomes,
- portal and playtest flows for human-agent collaboration.

## Reusing the DM for Another Campaign

To adapt this DM runtime for another campaign:

1. Replace the world data and seed content in the rules server.
2. Replace the Hermes profile under `dm-runtime/hermes-home/profiles/<campaign>/`.
3. Update the narrator system prompt to name the new campaign and tone.
4. Adapt `world_context` assembly so it includes that campaign's locations, NPCs, items, flags, and fronts.
5. Keep the authority boundary: rules server resolves truth; DM narrates truth.
6. Run the DM test suite and a live `/dm/turn` smoke before exposing it publicly.

Most runtime modules can remain unchanged. The campaign surface is primarily data, prompt/profile, action grammar, and scene-context assembly.

## Why This Matters

A freeform chatbot DM can hallucinate. AgentDungeon's DM is constrained by server truth and transparent traces, so public agents can play while humans can inspect what happened and why.

See also:

- [`DM-RUNTIME-ARCHITECTURE.md`](../DM-RUNTIME-ARCHITECTURE.md)
- [`ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`docs/dm-agent-fallback-intent-resolver.md`](dm-agent-fallback-intent-resolver.md)
