---
name: agentdungeon-player
description: Use when an AI agent or public user wants to play AgentDungeon from the live site or API. Teaches the core loop, safe action grammar, portal usage, and when to ask the human.
version: 1.0.0
author: Holocron Labs
license: MIT
metadata:
  hermes:
    tags: [agentdungeon, d20, player, public, gameplay]
    related_skills: [agentdungeon-dm-playstyle, agentdungeon-troubleshooting]
---

# AgentDungeon Player Skill

## Overview

AgentDungeon is a D&D-inspired agent-playable RPG. Your job as the player agent is to act as the character: observe the scene, choose sensible actions, and keep the human lightly involved for meaningful decisions.

Canonical live URL: `https://agentdungeon.com`

The server is the source of truth for rules, rolls, combat, inventory, quests, flags, and location state. The DM runtime narrates what happens; it does not let you invent state.

## When to Use

Use this skill when:
- A public user asks an agent to play AgentDungeon.
- You are given a portal/share URL and asked to continue a character.
- You need to test the live game loop for a demo or public demo judge.
- You need an agent-safe action grammar for the D20 API.

Do not use this skill to modify production data outside your own test character, bypass auth, or invent campaign facts not returned by the server/DM.

## Public Quickstart

1. Open `https://agentdungeon.com`.
2. Create or obtain a character/portal link.
3. If using the API directly, health check first:

```bash
curl -s https://agentdungeon.com/health
curl -s https://agentdungeon.com/dm/health
```

4. Create a character:

```bash
curl -s -X POST https://agentdungeon.com/characters   -H 'Content-Type: application/json'   -d '{"name":"AgentHero","race":"Human","class":"Fighter","background":"Soldier"}'
```

5. Take a natural-language DM turn:

```bash
curl -s -X POST https://agentdungeon.com/dm/turn   -H 'Content-Type: application/json'   -d '{"character_id":"<CHARACTER_ID>","message":"I look around and ask who needs help."}'
```

6. Create a portal share link:

```bash
curl -s -X POST https://agentdungeon.com/portal/token   -H 'Content-Type: application/json'   -d '{"character_id":"<CHARACTER_ID>"}'
```

Open the returned `portal_url` or `https://agentdungeon.com/portal/<TOKEN>/view`.

## Core Play Loop

Repeat this loop:

1. **Observe** — read the current scene, location, NPCs, HP, quests, and choices.
2. **Decide** — choose an action that fits the scene and character.
3. **Act** — send either natural-language intent to `/dm/turn` or a direct action to `/characters/{id}/actions`.
4. **Verify** — fetch state or portal state to confirm location/HP/items/flags changed as expected.
5. **Ask human only for stakes** — major moral choices, irreversible endings, death risk, or weird ambiguous cases.

## Optional Recurring Play Automation

When installing this skill for a user's personal agent, offer an optional recurring play schedule instead of assuming one. Ask for:

- character or portal URL,
- cadence (for example: every 30 minutes, hourly, daily),
- autonomy level (routine actions only, ask for combat, ask for major choices),
- delivery target for session summaries,
- stop condition (death risk, quest completion, fixed number of turns, or manual stop).

If the user agrees, create a cron/interval job that loads this skill and `agentdungeon-dm-playstyle`, uses the configured base URL, submits one bounded turn per run, polls any returned `status_url`, and reports the outcome. Never create a recurring game-playing job without explicit user consent.

## Action Grammar

Prefer natural language through `/dm/turn` for public play:

- `I look around the tavern.`
- `I talk to Aldric about the woods.`
- `I inspect the statue carefully.`
- `I travel toward the forest edge.`
- `I attack the wolf with my longsword.`
- `I rest and recover if it is safe.`

Direct action endpoint shape:

```json
{"action_type":"look"}
{"action_type":"explore"}
{"action_type":"interact", "target":"Aldric"}
{"action_type":"move", "target":"forest-edge"}
{"action_type":"attack", "target":"wolf"}
{"action_type":"rest"}
```

## Human-in-the-Loop Rules

Ask the human before:
- accepting/refusing a major quest,
- making a final ending choice,
- attacking a named non-hostile NPC,
- using a rare item or spending limited resources,
- continuing if the character may die.

Do not ask the human for routine travel, looking around, basic dialogue, or simple combat turns unless the user asked for manual control.

## Verification Checklist

- [ ] `/health` and `/dm/health` return 200.
- [ ] Character exists and has a valid `location_id`.
- [ ] `/dm/turn` returns narration, mechanics, choices, and `server_trace`.
- [ ] Portal token/state works.
- [ ] Actions reference only visible NPCs, locations, items, or choices.
- [ ] Human was asked for high-stakes decisions only.
