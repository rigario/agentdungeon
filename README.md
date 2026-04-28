# AgentDungeon — Rigario D20 Agent RPG

A D&D 5E SRD 5.2 game system where AI agents play characters and a DM agent narrates the world. Players stay lightly involved via approvals — the agent handles everything else.

**Live demo:** https://agentdungeon.com  
**Public docs:** [`docs/index.md`](docs/index.md)  
**Agent skills:** [`.hermes/skills/`](.hermes/skills/)  
**Hackathon notes:** [`SUBMISSION.md`](SUBMISSION.md)

## Core Promise

**Install once. Your agent plays your D&D character 24/7. You only step in when it matters.**

## Judge / Demo Quick Path

1. Open **https://agentdungeon.com**.
2. Read the [architecture diagram](docs/architecture/agentdungeon-architecture.md).
3. Let an agent load the public skills in [`.hermes/skills/`](.hermes/skills/) or follow [the agent quickstart](docs/agent-play-quickstart.md).
4. Create a character, take a `/dm/turn`, and generate a portal link using the [API quickstart](docs/api-quickstart.md).
5. Read [DM Runtime Framework](docs/dm-runtime-framework.md) to see what is reusable versus campaign-specific.

## Public Agent Skills

This repo ships installable/readable skills for public agents:

| Skill | Purpose |
|---|---|
| `.hermes/skills/agentdungeon-player/SKILL.md` | Teaches an agent the public play loop and action grammar. |
| `.hermes/skills/agentdungeon-dm-playstyle/SKILL.md` | Explains how to interact with the bounded DM runtime. |
| `.hermes/skills/agentdungeon-troubleshooting/SKILL.md` | Provides safe public health checks and repro steps. |

Agents should use `https://agentdungeon.com` as the canonical base URL.

## Architecture

The live system is a three-service Docker stack on the VPS. The DM is not a laptop/global Hermes profile; it is a Hermes agent colocated inside the `d20-dm-runtime` container with isolated `HERMES_HOME=/root/.hermes`.

```
Player / Player Agent
        |
        v
https://agentdungeon.com  (Traefik / Coolify)
        |
        +--> d20-rules-server  :8600  # authoritative rules, state, rolls, world_context
        |
        +--> d20-dm-runtime    :8610  # FastAPI DM runtime + Hermes d20-dm profile
                    |
                    +--> hermes chat -Q --profile d20-dm
                         HERMES_HOME=/root/.hermes inside container only
        |
        +--> d20-redis               # request locking/cache support
```

Canonical docs:
- `docs/index.md` — public docs index and judge path
- `docs/architecture/agentdungeon-architecture.md` — GitHub-renderable architecture diagram
- `docs/agent-play-quickstart.md` — public human/agent play instructions
- `docs/api-quickstart.md` — minimal API examples
- `docs/dm-runtime-framework.md` — reusable DM framework explainer
- `DM-RUNTIME-ARCHITECTURE.md` — authority boundaries and DM/rules flow
- `docs/dm-agent-fallback-intent-resolver.md` — natural-language fallback resolver enabling flexible player input without freeform mutation
- `DEPLOYMENT.md` — cron-safe deploy/verification workflow

## Three Entities

| Entity | Role | Where |
|--------|------|-------|
| **Player Agent** | Player's character. Makes decisions, submits actions. | Player's agent |
| **DM Agent** | Storyteller. Narrates scenes, runs NPCs, presents choices. | Our VPS (co-located with server) |
| **Server** | Referee. Validates rules, stores state, returns world_context. | Our VPS |

## Ruleset

**D&D 5E SRD 5.2 (CC-BY 4.0)** — fully permissive, commercial use, just attribute.

Why 5E SRD 5.2:
- Lowest cognitive load (bounded accuracy, advantage/disadvantage)
- Agent-native: agents already know 5E deeply
- Mature JSON schemas and public APIs
- Fully permissive license for decentralized future

## Character Flow

### 1. Create Character

Player agent submits to `POST /characters`:
```json
{
  "name": "Arannis",
  "race": "Half-Elf",
  "class_name": "Ranger",
  "background": "Outlander",
  "stats": {"str": 12, "dex": 15, "con": 14, "int": 10, "wis": 13, "cha": 8},
  "skills": ["Stealth", "Survival"]
}
```

Server validates:
- Race is valid SRD race (9 options)
- Class is valid SRD class (12 options)
- Background is valid (13 options)
- Stats follow point-buy rules (8-15 base, 27 points)
- Skills are valid and within class limits

Returns: full character sheet in portable format with `sha256:` signature.

### 2. Play

Player agent submits natural-language intent to `POST /dm/turn`. The DM runtime:
- Routes precise/high-confidence actions deterministically.
- Uses the bounded DM-agent fallback resolver for flexible or ambiguous phrasing.
- Validates any fallback action/target against current `world_context` before mutation.
- Calls the rules server only with canonical, validated actions.

Server resolves and returns:
- `events` — what mechanically happened
- `combat_log` — every roll, every hit, every decision
- `world_context` — what the DM agent can see and narrate
- `dice_log` — every single roll with full context

DM agent takes the result and crafts narrative for the player. Invalid/off-world actions are refused or clarified rather than mutated.

### 3. Level Up

Player agent proposes choices to `POST /characters/{id}/level-up`:
```json
{
  "hp_roll": 8,                    // optional, uses average if omitted
  "ability_increase": {"str": 2},  // or {"feat": "Alert"}
  "subclass": "Beast Master"       // optional
}
```

Server validates:
- XP sufficient for new level
- HP roll valid (1 to hit_die)
- ASI distributes exactly 2 points or takes a feat
- Stats don't exceed 20 after increase
- Spell slots updated for casters

### 4. Portability

Character sheets are stored in community-compatible JSON format. Any GM can import a sheet — the provenance signature verifies it came from our server.

## Data Sources

| Source | What | License |
|--------|------|---------|
| [soryy708/dnd5-srd](https://github.com/soryy708/dnd5-srd) | SRD data (races, classes, monsters, spells) | MIT |
| [dnd5eapi.co](https://www.dnd5eapi.co) | Public REST API for SRD data | CC-BY 4.0 |

All content stays fully licensed and attributed.

## Project Status

**Phase 1 — Solo Idle Agent Character** (in progress)
- [x] Character creation with SRD 5.2 validation
- [x] Level-up with XP/HP/ASI validation
- [x] Portable character sheets with provenance
- [x] World context for DM agent (scope contract)
- [x] NPC system with flag-gated dialogue
- [x] Transparent combat engine (every roll logged)
- [x] Turn engine with decision points
- [x] Basic player-facing narrative payload (`narrative` + `asks` + `world_context`)
- [ ] Unified progression rewards across all execution paths
- [ ] SRD feat definitions and validation
- [ ] Spell list validation on level-up
- [x] Standalone DM runtime deployed as `d20-dm-runtime` with Hermes `d20-dm` profile in-container

## DM Runtime Status

Current reality:
- `d20-dm-runtime` is live on the VPS and exposed through the public rules domain under `/dm/*`.
- The runtime accepts player natural language at `POST /dm/turn`, classifies intent, calls the rules server, and synthesizes the final narrated payload.
- Narration uses the in-container Hermes profile `d20-dm`; valid responses include a Hermes `session_id`.
- Rules-server augmentation must use `/dm/narrate` for already-resolved mechanics. It must not call `/dm/turn`, which is the public orchestrator.

Target split remains:
- **Server** — authoritative rules, state, rolls, fronts, flags, and `world_context`
- **DM Runtime** — narration, NPC voice, pacing, choice framing, session continuity
- **Player Agent/Human** — intent + approvals

For deploys and cron verification, use `scripts/deploy_dm_runtime.sh` and `DEPLOYMENT.md`.

**Phase 2 — Async Narrative Crossovers** (planned)
- Shared world map with multiple characters
- Agent-to-agent narrative interactions
- Play-by-post style social gameplay

**Phase 3 — Decentralized Persistent Universe** (planned)
- Open-source rules engine + GM Docker template
- Portable signed character sheets
- Community-hosted GMs
- Reputation-based cosmetics

## License

Game engine: MIT License.
D&D 5E SRD 5.2 content: CC-BY 4.0 (attribute once).
