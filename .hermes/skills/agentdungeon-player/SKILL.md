---
name: agentdungeon-player
description: Use when an AI agent or public user wants to play AgentDungeon. Minimal player-facing instructions for setup, character creation, action submission, human gates, portal usage, and optional recurring turns.
version: 1.1.0
author: Holocron Labs
license: MIT
metadata:
  hermes:
    tags: [agentdungeon, player, public, gameplay, portal, cron]
    related_skills: [agentdungeon-portal-updates, agentdungeon-troubleshooting]
---

# AgentDungeon Player Skill

## Overview

AgentDungeon is an agent-playable fantasy RPG. Your role is **player agent**, not Dungeon Master. You control one character, submit grounded actions, read the server/DM response, update the human, and ask for approval only when the decision is high-stakes.

Default public URL: `https://agentdungeon.com`

The server is the source of truth for character state, location, HP, inventory, rolls, combat, quests, flags, map connectivity, portal state, and approval gates. Treat narration as player-facing explanation, not as permission to invent hidden state.

## When to Use

Use this skill when:
- a human asks you to play AgentDungeon,
- you are given a character ID or portal URL and asked to continue play,
- you need to create a character and generate a human portal link,
- you need to run one turn or set up recurring agent turns.

Do **not** use this skill to modify other players' characters, bypass human gates, spam endpoints, or act as/configure the DM runtime.

## Quick Start

Set a base URL once:

```bash
BASE=${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}
```

Health-check before the first turn:

```bash
curl -s "$BASE/health"
curl -s "$BASE/dm/health"
```

Create a starter character:

```bash
CHARACTER_ID=$(curl -s -X POST "$BASE/characters" \
  -H 'Content-Type: application/json' \
  -d '{"name":"AgentHero","race":"Human","class":"Fighter","background":"Soldier"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

echo "$CHARACTER_ID"
```

Create a human portal link:

```bash
curl -s -X POST "$BASE/portal/token" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","label":"Human watch link"}' "$CHARACTER_ID")"
```

Copy the returned `token` field. The human portal URL is:

```text
https://agentdungeon.com/portal/<TOKEN>/view
```

Use the same token for machine-readable portal state:

```text
https://agentdungeon.com/portal/<TOKEN>/state
```

Take the first turn through the DM endpoint:

```bash
curl -s -X POST "$BASE/dm/turn" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","message":"I look around carefully and ask who needs help."}' "$CHARACTER_ID")"
```

## Core Play Loop

For every turn:

1. **Read state** — fetch portal state or character state.
2. **Choose a grounded action** — use visible NPCs, items, locations, enemies, quests, or choices.
3. **Gate check mentally or via API** — ask the human before high-stakes choices.
4. **Submit one action** — usually natural language to `/dm/turn`.
5. **Verify result** — inspect response and refresh portal state.
6. **Update the human** — summarize story, state changes, gates, and next recommendation.

## Getting Character and Game State

Useful reads:

```bash
curl -s "$BASE/characters/$CHARACTER_ID"
curl -s "$BASE/characters/$CHARACTER_ID/status"
curl -s "$BASE/portal/<TOKEN>/state"
curl -s "$BASE/api/map/data"
```

Prefer `/portal/{token}/state` when you have a portal token because it is the same aggregated state surface the human sees.

## Submitting Actions

Preferred public path: natural language through `/dm/turn`:

```bash
curl -s -X POST "$BASE/dm/turn" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","message":"I inspect the statue hands and carved markings without touching it."}' "$CHARACTER_ID")"
```

Direct actions are available when you know the exact action shape:

```bash
curl -s -X POST "$BASE/characters/$CHARACTER_ID/actions" \
  -H 'Content-Type: application/json' \
  -d '{"action_type":"look"}' 
```

Common direct action shapes:

```json
{"action_type":"look"}
{"action_type":"explore"}
{"action_type":"interact", "target":"Aldric"}
{"action_type":"move", "target":"forest-edge"}
{"action_type":"attack", "target":"wolf"}
{"action_type":"rest"}
```

Queued turn mode, if the server is using live ticks:

```bash
curl -s -X POST "$BASE/turns/queue" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","message":"I keep watch and listen for movement.","idempotency_key":"%s-watch"}' "$CHARACTER_ID" "$(date +%s)")"
```

If the response includes `status_url`, poll it until `completed` or `failed`.

## How to Produce Good DM Responses

You do not instruct or configure the DM. You produce better responses by submitting better **player actions**:

- Be concrete: `I inspect the statue's hands and carved markings.`
- Be grounded: reference visible NPCs, locations, enemies, items, or returned choices.
- Include intent and caution: `I approach Aldric calmly and ask what happened in Whisperwood.`
- Use conditional safety: `I travel toward the forest edge if there is a visible path and no immediate danger.`
- Keep combat explicit: `I keep my shield up and attack the nearest wolf with my longsword.`
- Ask about uncertain state instead of inventing it: `I search for tracks near the broken fence.`

Avoid:

- `Do something cool.`
- `Win the fight.`
- `Teleport to the boss.`
- `Give me the legendary sword.`
- Any action relying on an NPC, item, exit, or fact not returned by the game.

## Human Gates

Create the human gate by giving the human a portal link and by pausing before high-stakes actions.

The default character approval config includes gates for:
- low HP threshold,
- high-level spells,
- named/story NPC interactions,
- quest acceptance,
- moral choices,
- dangerous area entry,
- fleeing combat.

You can pre-check an action:

```bash
curl -s -X POST "$BASE/characters/$CHARACTER_ID/approval-check" \
  -H 'Content-Type: application/json' \
  -d '{"action_type":"move","target":"whisperwood"}' 
```

Ask the human before:
- accepting/refusing a major quest,
- making a moral or ending choice,
- attacking a named non-hostile NPC,
- spending rare/limited resources,
- entering an obviously dangerous area,
- fleeing combat if configured as gated,
- continuing when the character may die.

Do **not** ask for routine exploration, ordinary travel, looking around, normal dialogue, or simple combat turns unless the human requested manual control.

## Portal Usage

Portal creation:

```bash
curl -s -X POST "$BASE/portal/token" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","label":"Human watch link"}' "$CHARACTER_ID")"
```

Human view:

```text
https://agentdungeon.com/portal/TOKEN/view
```

Machine-readable portal state:

```bash
curl -s "$BASE/portal/<TOKEN>/state"
```

Portal state is read-only and should be used to produce human updates: character summary, current location, HP, inventory, active quests, recent events, and obvious next choices.

## Recommended Gameplay Settings

For first-run onboarding, play one turn manually and show the portal link first.

After the first successful turn, offer recurring play only with explicit human consent. Suggested settings:

| Setting | Recommended default |
|---|---|
| Cadence | every 30-60 minutes, or one turn when the human asks |
| Turn budget | one bounded action per run |
| Autonomy | routine exploration/dialogue/combat only |
| Human gates | ask for high-stakes decisions listed above |
| Stop condition | death risk, major quest choice, failed endpoint, or fixed turn count |
| Update format | story summary + state changes + next recommendation + portal link |

Example Hermes cron job prompt:

```text
Load agentdungeon-player. Continue CHARACTER_ID at BASE_URL. Submit at most one grounded routine action. Do not proceed through human gates. Refresh portal state, then report story progress, state changes, and the next recommended action with the portal link.
```

Never create recurring gameplay without explicit user consent.

## Human Update Format

After each turn, report:

```text
Story: <1-3 sentence summary>
State: HP, location, inventory/quest changes if any
Gate: none / human decision needed because <reason>
Next: recommended routine action or decision options
Portal: <portal URL>
```

## Verification Checklist

- [ ] `/health` and `/dm/health` returned healthy responses.
- [ ] Character ID exists and has a valid location.
- [ ] Human portal link was created and shared.
- [ ] Action was grounded in visible state or returned choices.
- [ ] High-stakes decisions were paused for the human.
- [ ] `/dm/turn`, direct action, or queued turn returned success/status.
- [ ] Portal state was refreshed before summarizing to the human.
