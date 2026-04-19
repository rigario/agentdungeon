# Rigario D20 Agent RPG

A D&D 5E SRD 5.2 game system where AI agents play characters and a DM agent narrates the world. Players stay lightly involved via approvals — the agent handles everything else.

## Core Promise

**Install once. Your agent plays your D&D character 24/7. You only step in when it matters.**

## Architecture

```
Player Agent (player's agent)          DM Agent (our VPS, storyteller)
─────────                               ────────
Creates character ──────────────────→ Narrates arrival
Makes level-up choices               "You awaken in Thornhold..."
Submits actions                      Voices NPCs
                                      Presents choices

Server (our VPS, referee)
─────────
Validates all 5E mechanical rules
Stores portable character sheets
Manages world state and combat
Returns world_context to DM agent
```

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

Player agent submits actions to server. Server resolves and returns:
- `events` — what mechanically happened
- `combat_log` — every roll, every hit, every decision
- `world_context` — what the DM agent can see and narrate
- `dice_log` — every single roll with full context

DM agent takes the world_context and crafts narrative for the player.

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
- [ ] XP rewards from combat
- [ ] SRD feat definitions and validation
- [ ] Spell list validation on level-up
- [ ] DM agent implementation

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
