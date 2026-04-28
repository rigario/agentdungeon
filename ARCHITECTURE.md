# Architecture — Rigario D20 Agent RPG

## System Overview

Current implementation status:
- **Server/referee is real and running** — rules, state, combat, turn simulation, fronts, flags, and `world_context` are implemented in `d20-rules-server`.
- **DM runtime is real and running** — `d20-dm-runtime` accepts `/dm/turn`, routes to the rules server, and invokes Hermes narration in-container.
- **Hermes `d20-dm` profile is container-only** — live profile is `/root/.hermes/profiles/d20-dm` inside the VPS `d20-dm-runtime` container. Do not create/use laptop `~/.hermes/profiles/d20-dm`.

See `DM-RUNTIME-ARCHITECTURE.md` for authority boundaries and `DEPLOYMENT.md` for cron-safe deploy/verification. The DM-agent fallback intent resolver is documented in `docs/dm-agent-fallback-intent-resolver.md`.

Three independent entities that never mix responsibilities:

```
┌─────────────────┐
│ Player / Agent  │
└────────┬────────┘
         │ HTTPS: agentdungeon.com
         ▼
┌─────────────────────────────────────────────────────┐
│ VPS Docker Compose project: /home/admin/apps/d20    │
│                                                     │
│  d20-rules-server (:8600)                           │
│    - validates rules, rolls, state, world_context   │
│                                                     │
│  d20-dm-runtime (:8610)                             │
│    - /dm/turn public player-input orchestrator      │
│    - /dm/narrate narrate-only internal endpoint     │
│    - Hermes agent inside container only             │
│      HERMES_HOME=/root/.hermes                      │
│      profile=/root/.hermes/profiles/d20-dm          │
│                                                     │
│  d20-redis                                          │
│    - lock/cache support                             │
└─────────────────────────────────────────────────────┘
```

## Entity Responsibilities

### Server (Referee)

**Single responsibility: validate and store.**

- Validates all mechanical rules against SRD 5.2:
  - Character creation (point-buy, valid race/class/background)
  - Level-up (XP thresholds, HP, ASI, spell slots)
  - Combat (attack rolls, damage, AC, hit points)
  - World state (locations, encounters, NPCs)
- Stores character sheets in portable JSON format
- Generates provenance signatures for every sheet change
- Returns `world_context` to the DM agent — the scope of what exists

The server **never** narrates. It never creates content. It validates and returns structured data.

### DM Agent (Storyteller)

**Single responsibility: narrate within server-validated bounds and interpret ambiguous player phrasing into bounded candidate actions.**

- Receives `world_context` from the server after each action
- Crafts narrative from validated data:
  - Describes locations using location description
  - Voices NPCs using their personality and flag-gated dialogue
  - Describes combat using combat_log
  - Presents choices from `asks`
- Interprets flexible/ambiguous player phrasing through the fallback intent resolver when deterministic routing cannot safely act
- Follows the scope contract:
  - May describe ONLY what's in world_context
  - Must NOT invent additional NPCs, locations, items, or events

The DM agent **never** validates rules and never modifies character sheets directly. In fallback mode it may propose a canonical action/target, but the runtime validates that proposal against `world_context` and the server performs any actual mutation.

### Player Agent (Character)

**Single responsibility: make decisions within the world.**

- Creates character (race, class, background, stats, skills)
- Proposes level-up choices (HP roll, ASI, subclass, feat)
- Submits actions to server
- Responds to DM agent's narrative
- Approves high-impact moments with the human

The player agent **never** validates its own actions. It proposes, the server validates.

## Data Flow

### Character Creation

```
Player Agent                   Server                    DM Agent
─────────                      ──────                    ────────
{race, class, stats, skills} → Validate point-buy      →
                              → Validate race/class     →
                              → Build sheet from SRD    →
                              → Sign with sha256        →
                              → Store in DB             →
                              → Return portable sheet   → Narrate arrival
```

### Turn / Action

```text
Player Agent                   DM Runtime                 Server
─────────                      ──────────                 ──────
"I enter the tavern"         → deterministic route      → Load character state
                              → fallback resolver if       Validate action/target
                                phrasing is ambiguous      Resolve mechanics
                              → validated canonical      → Return events/world_context
                                action only              →
                              → synthesize/narrate final player-facing payload
```

The fallback resolver lets players use flexible language, but it does not bypass server authority. Low-confidence/general messages can become `execute`, `clarify`, `refuse`, or `narrate_noop`; only a validated `execute` path reaches mutation endpoints.

### Level Up

```
Player Agent                   Server                    DM Agent
─────────                      ──────                    ────────
{hp_roll: 8, str: +2}        → Check XP threshold     →
                              → Validate HP range       →
                              → Validate ASI rules      →
                              → Update stats/sheet      →
                              → Re-sign sheet           → Narrate growth
                                                        → "You feel stronger"
```

## World Context (Hallucination Guardrail)

The `world_context` field in turn results is the DM agent's scope contract. It tells the DM agent exactly what exists and what it can describe:

```json
{
  "location": {
    "id": "thornhold",
    "name": "Thornhold",
    "biome": "town",
    "description": "A small walled town at the edge of the Whisperwood...",
    "hostility_level": 1,
    "recommended_level": 1
  },
  "connections": [
    {"id": "forest-edge", "name": "Whisperwood Edge"},
    {"id": "south-road", "name": "South Road"}
  ],
  "npcs": [
    {
      "id": "npc-aldric",
      "name": "Aldric the Innkeeper",
      "archetype": "innkeeper",
      "personality": "Round, tired, perpetually wiping mugs...",
      "dialogue": [
        {
          "context": "greeting",
          "template": "Welcome to The Rusty Tankard..."
        },
        {
          "context": "hollow_eye_confessed",
          "template": "...Fine. Yes. They pay me to not look...",
          "requires_flag": "aldric_lying",
          "clue_reward": {"flag": "aldric_confessed", "value": "1"}
        }
      ],
      "trades": [
        {"buy": "Rations (1 day)", "price": 2},
        {"buy": "Healing Potion", "price": 50}
      ]
    }
  ],
  "encounters": [...],
  "flags": {
    "aldric_lying": {"value": "1", "source": "conversation"}
  },
  "fronts": [
    {"id": "main-seal", "name": "The Seal Cracks", "stage": 1}
  ],
  "scope_contract": "SCOPE CONTRACT — The agent MAY describe ONLY the items in this world_context. The agent MUST NOT invent additional NPCs, locations, items, or plot hooks not present in this list."
}
```

The scope contract is the key anti-hallucination mechanism. The DM agent can flesh out what exists, but cannot create new content.

## NPC System

NPCs have:
- **Personality** — how they think and act (used by DM agent to voice them)
- **Dialogue templates** — what they say, with flag gates
- **Clue rewards** — flags set when player discovers information
- **Trades** — what they sell
- **Quests** — what they offer

Dialogue is flag-gated. An NPC's `hollow_eye_confessed` line only appears in the world_context after the `aldric_lying` flag is set. The server controls what the DM agent sees — the DM agent cannot access dialogue that hasn't been unlocked.

## Transparent Logging

Every action produces three logs:

### Dice Log (every roll)
```json
{
  "type": "d20",
  "raw": 17,
  "modifier": 3,
  "total": 20,
  "crit": false,
  "fumble": false,
  "context": "Attack (Arannis → Cultist)"
}
```

### Decision Log (every choice the server made)
```json
{
  "step": 1,
  "decision": "Random exploration → forest-edge",
  "reasoning": "Goal=explore. Randomly chose from: [forest-edge, south-road]"
}
```

### Combat Log (round-by-round)
```json
{
  "round": 1,
  "turns": [
    {"actor": "Arannis", "action": "attack", "target": "Cultist 1", "roll": 18, "hit": true, "damage": 7},
    {"actor": "Cultist 1", "action": "attack", "target": "Arannis", "roll": 12, "hit": false}
  ]
}
```

The DM agent uses these logs to narrate. The player agent uses them to understand what happened. Both are bounded by the same validated data.

## Level-Up Validation

The server validates every mechanical rule:

| Rule | Validation |
|------|-----------|
| XP sufficient | `current_xp >= XP_THRESHOLDS[new_level]` |
| Level increment | `new_level == current_level + 1` |
| Max level | `new_level <= 20` |
| HP roll range | `1 <= hp_roll <= hit_die` |
| ASI at right level | `level in ASI_LEVELS[class]` |
| ASI total | `sum(ability_increase.values()) == 2` |
| Stat cap | `stat + increase <= 20` |
| Feat alternative | `{"feat": "Alert"}` instead of ability_increase |
| Spell slots | Auto-calculated for casters |

## Character Sheet (Portable Format)

```json
{
  "version": "5.2",
  "name": "Arannis",
  "race": {"name": "Half-Elf", "size": "Medium", "traits": [...]},
  "classes": [{"name": "Ranger", "level": 2, "hit_die": 10, "spellcasting": "", "features": [...]}],
  "background": {"name": "Outlander"},
  "ability_scores": {"str": 13, "dex": 16, "con": 15, "int": 11, "wis": 14, "cha": 9},
  "hit_points": {"max": 22, "current": 22, "temporary": 0},
  "armor_class": {"value": 13, "description": "Unarmored"},
  "skills": {"Athletics": true, "Survival": true, "Stealth": true},
  "saving_throws": {"str": true, "dex": true},
  "equipment": ["Longsword", "Shortsword", "Scale Mail", "Longbow"],
  "spell_slots": {},
  "feats": [],
  "conditions": {},
  "xp": 300,
  "provenance": {
    "data_source": "soryy708/dnd5-srd (MIT License)",
    "created_at": "2026-04-14T09:00:06Z",
    "signature": "sha256:27a5ce3fd967463c"
  }
}
```

The sheet is the same format at creation, after every level-up, and when exported. Any GM can import it — the provenance signature verifies it came from our server.

## Content Sources

| Source | What | License |
|--------|------|---------|
| [soryy708/dnd5-srd](https://github.com/soryy708/dnd5-srd) | Races, classes, monsters, spells, equipment | MIT |
| [dnd5eapi.co](https://www.dnd5eapi.co) | Public REST API for SRD data | CC-BY 4.0 |

SRD 5.2 content is used for:
- Race definitions (9 races with traits, ability bonuses)
- Class definitions (12 classes with hit die, proficiencies, features)
- Background definitions (13 backgrounds with skill proficiencies)
- Skill names and ability associations
- Equipment and starting gear
- Spell data and progression
- Monster stat blocks for encounters
- XP thresholds and proficiency bonuses

## API Endpoints

### Characters
- `POST /characters` — Create character with SRD validation
- `GET /characters/{id}` — Get portable character sheet
- `PATCH /characters/{id}` — Update character fields
- `DELETE /characters/{id}` — Archive character
- `POST /characters/{id}/level-up` — Level up with validation

### Turns
- `POST /characters/{id}/turn/start` — Submit action, get turn result with world_context
- `GET /characters/{id}/turn/result/{turn_id}` — Get specific turn result
- `GET /characters/{id}/turn/latest` — Get most recent turn

### World
- `GET /narrative/fronts` — Active story fronts
- `GET /narrative/flags/{character_id}` — Character's narrative flags
- `GET /narrative/mark/{character_id}` — Mark of the Dreamer status

### Health
- `GET /health` — Server health check
