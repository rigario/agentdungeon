# AgentDungeon

AgentDungeon is an agent-playable fantasy RPG system: an AI player controls a character, an AI Dungeon Master narrates, and an authoritative rules server owns state, rolls, combat, inventory, quests, flags, and world context.

- **Live demo:** https://agentdungeon.com
- **GitHub:** https://github.com/rigario/agentdungeon
- **Public docs:** [`docs/index.md`](docs/index.md)
- **Agent skills:** [`.hermes/skills/`](.hermes/skills/)

## Core promise

**Install once. Your agent can keep playing your character. You only step in when decisions matter.**

## Quick path

1. Open **https://agentdungeon.com**.
2. Read the [architecture diagram](docs/architecture/agentdungeon-architecture.md).
3. Let an agent load the public skills in [`.hermes/skills/`](.hermes/skills/) or follow [the agent quickstart](docs/agent-play-quickstart.md).
4. Create a character, take a `/dm/turn`, and generate a portal link using the [API quickstart](docs/api-quickstart.md).
5. Read [DM Runtime Framework](docs/dm-runtime-framework.md) to see what is reusable versus campaign-specific.

## Public agent skills

| Skill | Purpose |
|---|---|
| `.hermes/skills/agentdungeon-player/SKILL.md` | Required player skill: onboarding, character creation, grounded actions, human gates, portal usage, and optional recurring turns. |
| `.hermes/skills/agentdungeon-portal-updates/SKILL.md` | Optional state/update skill: read portal/server state and produce concise story updates for the human. |
| `.hermes/skills/agentdungeon-troubleshooting/SKILL.md` | Optional diagnostics: safe public health checks and repro steps when play or portal access fails. |

DM-runtime/contributor-only guidance lives separately under `.hermes/dm-skills/` so public player agents do not confuse player behavior with DM configuration.

The public player skills default to `https://agentdungeon.com`, but agents should override the base URL when playing against a self-hosted deployment.

## Architecture

```text
Player / Player Agent
        |
        v
Public HTTPS endpoint
        |
        +--> rules server      # authoritative rules, state, rolls, world context
        |
        +--> DM runtime        # intent routing, narration, choice framing
        |          |
        |          +--> Hermes profile inside the runtime container
        |
        +--> Redis             # optional request locking/cache support
```

## Authority boundaries

| Entity | Owns | Must not do |
|---|---|---|
| Player agent | Intent, routine decisions, asking the human for high-stakes choices | Invent hidden state or bypass the server |
| DM runtime | Narration, NPC voice, pacing, translating ambiguous phrasing into bounded candidate actions | Mutate state directly or invent facts outside `world_context` |
| Rules server | State, rules, rolls, combat, inventory, quests, flags, portal data | Freeform narration |

## Character flow

### 1. Create character

`POST /characters` accepts race/class/background/stat choices and returns a portable signed character sheet.

### 2. Play

`POST /dm/turn` accepts natural-language intent. The DM runtime routes or clarifies the intent, the rules server resolves mechanics, and the DM returns player-facing narration grounded in server state.

### 3. Share progress

`POST /portal/token` creates a read-only portal link so a human can watch character state without inspecting raw API JSON.

## Data sources and licensing

The engine is MIT licensed. Any external rules/reference data used by an installation must be sourced and attributed according to that source's license. This repository keeps rule handling in code and avoids committing private/generated reference dumps.

## Project status

Core systems currently implemented:

- Character creation and level-up validation
- Portable character sheets with provenance signatures
- World context and scoped DM narration
- NPCs, flags, locations, encounters, key items, and portal views
- Transparent combat logging
- DM runtime with bounded intent routing and narration
- Queued live-tick turn receipts and status polling

Planned extensions:

- More campaign templates
- Multi-character social/crossover play
- Stronger installer flow for recurring autonomous play sessions
- Community-hosted deployments
