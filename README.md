# AgentDungeon

AgentDungeon is an agent-playable fantasy RPG system: an AI player controls a character, an AI Dungeon Master narrates, and an authoritative rules server owns state, rolls, combat, inventory, quests, flags, and world context.

- **Live demo:** https://agentdungeon.com
- **GitHub:** https://github.com/rigario/agentdungeon
- **Public docs:** [`docs/index.md`](docs/index.md)
- **Agent skills:** [`.hermes/skills/`](.hermes/skills/)

## Core promise

**Install once. Your agent can keep playing your character. You only step in when decisions matter.**

## Quick path

Prerequisite: an AI agent that can load Markdown skills and call web APIs. For Hermes, install/setup Hermes first, then load the public skill below.

1. Open **https://agentdungeon.com** to verify the live game is reachable; the human watches through a portal while the agent plays.
2. Read the [architecture diagram](docs/architecture/agentdungeon-architecture.md).
3. Let an agent load the public skills in [`.hermes/skills/`](.hermes/skills/) or follow [the agent quickstart](docs/agent-play-quickstart.md).
4. Create a character, take a `/dm/turn`, and generate a portal link using the [API quickstart](docs/api-quickstart.md).
5. Read [DM Runtime Framework](docs/dm-runtime-framework.md) to see what is reusable versus campaign-specific.

## Public agent skills

| Skill | Raw Markdown | Purpose |
|---|---|---|
| `.hermes/skills/agentdungeon-player/SKILL.md` | [raw](https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-player/SKILL.md) | Required player skill: onboarding, character creation, grounded actions, human gates, portal usage, and optional recurring turns. |
| `.hermes/skills/agentdungeon-portal-updates/SKILL.md` | [raw](https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-portal-updates/SKILL.md) | Optional state/update skill: read portal/server state and produce concise story updates for the human. |
| `.hermes/skills/agentdungeon-troubleshooting/SKILL.md` | [raw](https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-troubleshooting/SKILL.md) | Optional diagnostics: safe public health checks and repro steps when play or portal access fails. |

Agents should fetch the raw Markdown URLs above directly instead of spending turns browsing GitHub UI pages or cloning the full repository. A skill is a Markdown instruction file that tells the agent how to create/resume characters, ask for human gates, play turns, and report state.

```bash
mkdir -p ~/.hermes/skills/agentdungeon-player
curl -fsSL https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-player/SKILL.md \
  -o ~/.hermes/skills/agentdungeon-player/SKILL.md
hermes -s agentdungeon-player
```

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

### 1. Create or resume character

Player agents should first ask whether the human wants to resume an existing character or create a new one. For new characters, character creation is human-in-the-loop: the agent asks for or gets explicit delegation on name, class, race, background, stats/point-buy, personality/risk tolerance, and post-creation autonomy before calling `POST /characters`. For resume, the agent verifies the character ID or portal token and produces a Resume Card so play can continue later.

### 2. Play

`POST /dm/turn` accepts natural-language intent. The DM runtime routes or clarifies the intent, the rules server resolves mechanics, and the DM returns player-facing narration grounded in server state.

### 3. Share progress

`POST /portal/token` creates a read-only portal link so a human can watch character state without inspecting raw API JSON.

## Data sources, licensing, and credits

The original AgentDungeon engine code is MIT licensed; see [`LICENSE`](LICENSE). Required credits and third-party notices live in [`NOTICE.md`](NOTICE.md) and on the public `/credits` page.

AgentDungeon is a 5E-compatible project. Where it uses or adapts rules terms, classes, species/races, mechanics, spells, equipment, or other reference material from the Dungeons & Dragons System Reference Document, that material is credited to Wizards of the Coast LLC and used under Creative Commons Attribution 4.0 International. Source: https://www.dndbeyond.com/srd. This project is not affiliated with, endorsed, sponsored, or specifically approved by Wizards of the Coast LLC.

Any future external art, music, icon, font file, copied text, dataset, or rules/reference source must be added to [`NOTICE.md`](NOTICE.md) before it is published on the repo or website.

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
