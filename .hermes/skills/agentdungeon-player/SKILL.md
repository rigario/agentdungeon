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

**Character creation is the exception to normal autonomy.** Treat character creation as a highly human-involved onboarding conversation, not a background setup task. The human must choose or explicitly delegate most character identity and build decisions before you POST `/characters`.

Default public URL: `https://agentdungeon.com`

The server is the source of truth for character state, location, HP, inventory, rolls, combat, quests, flags, map connectivity, portal state, and approval gates. Treat narration as player-facing explanation, not as permission to invent hidden state.

## When to Use

Use this skill when:
- a human asks you to play AgentDungeon,
- you are given a character ID or portal URL and asked to continue play,
- you need to create a character and generate a human portal link,
- you need to run one turn or set up recurring agent turns.

Do **not** use this skill to modify other players' characters, bypass human gates, spam endpoints, or act as/configure the DM runtime.

## New vs Resume Decision

At the start of onboarding, determine whether the human wants to **resume an existing character** or **create a new one**.

- If the human provides a `character_id`, portal URL, portal token, or says "continue/resume", resume that character.
- If the human says "new character" or has no prior character, run the full human-involved character creation protocol below.
- If unclear, ask one concise question: "Do you want to resume an existing character or create a new one? If resuming, send the character ID or portal link."
- Do not browse or claim other players' characters from public endpoints. Resume only a character the human identifies or that the authenticated user/agent is authorized to operate.

To resume from a portal URL, extract the token from the path segment between `/portal/` and `/view` or `/state`, fetch portal state, and use the returned `character_id` if present:

```bash
PORTAL_URL='https://agentdungeon.com/portal/<TOKEN>/view'
TOKEN=$(python3 - "$PORTAL_URL" <<'PY'
import re, sys
url = sys.argv[1]
m = re.search(r'/portal/([^/]+)/(?:view|state)', url)
print(m.group(1) if m else '')
PY
)
curl -s "$BASE/portal/$TOKEN/state"
```

If both a character ID and portal URL are provided, verify that portal state points to the same character before proceeding. If they differ, stop and ask the human which one to use. Before any recurring or long-running play, also validate the portal token with `GET /portal/token/{token}/validate`; if it is invalid, expired, or revoked, create a fresh portal token and share the new view link before continuing.

To resume from a character ID:

```bash
CHARACTER_ID='<KNOWN_CHARACTER_ID>'
curl -s "$BASE/characters/$CHARACTER_ID/status"
curl -s "$BASE/characters/$CHARACTER_ID"
```

If the response is missing, archived, unauthorized, or unhealthy, explain that the character could not be resumed and ask whether to retry with another ID/link or create a new character.

## What to Store for Resume

After creating or resuming a character, give the human a compact **Resume Card** and include it in any recurring-turn cron prompt. Do not rely only on chat memory. If the server exposes a future play-config field, sync these same autonomy settings there; until then, the Resume Card is the portable source of truth.

Store/share these fields:

```text
AgentDungeon Resume Card
Base URL: <actual BASE, default https://agentdungeon.com>
Character ID: <character_id>
Character name: <name>
Portal view: https://agentdungeon.com/portal/<TOKEN>/view
Portal state: https://agentdungeon.com/portal/<TOKEN>/state
Human involvement: <hands-on / agent-led / guided / custom>
Autonomy rules: <what the agent may do without asking>
Hard gates: <choices that always require human approval>
Last verified: <timestamp and one-line state summary>
```

For scheduled or recurring play, the future prompt must be self-contained and include at minimum: base URL, character ID, portal state URL or token, human involvement setting, autonomy rules, hard gates, and the instruction to submit at most one grounded routine action before refreshing portal state.

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

Before creating anything, ask whether the human wants to resume an existing character or create a new one. If resuming, verify the character/portal state and skip the creation flow.


## New Player Guided Onboarding Script

When the human is new, lead them. Do not assume they know D&D terms, endpoint names, or what choices matter. Use plain English and offer bounded options.

Recommended first message:

```text
Welcome to AgentDungeon. I can either resume an existing character or help you make a new one.

1. Resume: send me a portal link or character ID.
2. New character: I'll guide you step by step. First I'll ask how involved you want to be, then name, class, point-buy, background/style, and how much autonomy you want me to have during play.

Which do you want: resume or new?
```

If creating a new character, explain the flow before asking details:

```text
Character creation is where you decide who this person is. I'll make suggestions, but I won't finalize name, class, stats, or personality unless you choose or explicitly delegate them. After that, I'll create a portal link so you can watch the sheet and state, then I'll take one safe first turn and pause if a meaningful decision appears.
```

When available, prefer a live metadata endpoint for current creation options; otherwise use these built-in summaries and supported lists. Use short class summaries for humans who do not know what to pick:

| Class | Plain-English playstyle |
|---|---|
| Barbarian | Tough front-line bruiser; simple, aggressive, hard to kill. |
| Bard | Charismatic trickster/support; social, magical, versatile. |
| Cleric | Armored divine caster; healing, protection, undead/faith themes. |
| Druid | Nature caster; wilderness, animals, control, primal magic. |
| Fighter | Reliable weapon expert; easiest martial class, strong in combat. |
| Monk | Fast martial artist; mobility, discipline, unarmed combat. |
| Paladin | Holy knight; durable, moral choices, burst damage, protection. |
| Ranger | Wilderness hunter; tracking, bows/blades, exploration. |
| Rogue | Sneaky skill expert; scouting, locks, precision attacks. |
| Sorcerer | Innate magic; dramatic spellcaster, charisma, raw power. |
| Warlock | Pact-bound caster; eerie patron, short-rest magic, strong flavor. |
| Wizard | Studied spellcaster; flexible magic, fragile but powerful. |

For point buy, if the human wants help, offer a recommended spread and explain it in one sentence. Example: "For Fighter, I recommend STR 15, DEX 14, CON 13, WIS 12, INT 10, CHA 8: strong melee, decent defense, and enough awareness to survive." Then ask for approval or edits.


Create a starter character only after the human completes the onboarding choices below. **Do not silently default name/class/build.**

Minimum guided flow before `POST /characters`:

1. Ask how involved the human wants to be during creation and future play:
   - `Hands-on creation + hands-on play` — ask before most build and story choices.
   - `Hands-on creation + agent-led play` — human chooses the build; agent handles routine turns after creation.
   - `Guided quick build` — human answers name/class/core fantasy; agent proposes the rest for confirmation.
   - `Surprise me, but confirm` — agent drafts everything, then asks for approval before creation.
2. Ask for the character **name**. If the human has no name yet, offer 3-5 options and let them choose.
3. Ask the human to choose a **class**. Supported classes: Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard.
4. Ask whether the human wants to assign the 27-point buy themselves or wants the agent to propose it:
   - Human-assigned: collect exact `str`, `dex`, `con`, `int`, `wis`, `cha` values, each 8-15, exactly 27 points.
   - Agent-proposed: propose a class-appropriate spread, explain the tradeoff in one sentence, and ask for confirmation before use.
5. Ask for preferences or delegation on race, background, skills, languages, spell/caster flavor, personality, risk tolerance, and how often to pause for choices. Use defaults only for fields the human explicitly delegates. If the human does not know the race/background options, offer 3-5 plain-English recommendations instead of dumping every rule detail.
6. Present a final one-screen character plan and ask for confirmation before calling the API.

Example API call after confirmed choices:

```bash
CHARACTER_ID=$(curl -s -X POST "$BASE/characters" \
  -H 'Content-Type: application/json' \
  -d '{"name":"<HUMAN_CHOSEN_NAME>","race":"<CONFIRMED_RACE>","class":"<CONFIRMED_CLASS>","background":"<CONFIRMED_BACKGROUND>","stats":{"str":15,"dex":14,"con":13,"int":10,"wis":12,"cha":8}}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

echo "$CHARACTER_ID"
```

If the human chooses agent-proposed point buy, still include the confirmed `stats` object instead of relying on the server default when possible.

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

## Character Creation Protocol

Character creation is a **human-in-the-loop scene**, not just a setup call. Slow down and make the human feel ownership over the avatar.

Before creating a character, ask in this order:

1. **Involvement level:** "How involved do you want to be — hands-on for every build choice, guided quick build, or agent-proposed build with confirmation?"
2. **Name:** "What is your character's name?" If they are unsure, provide a short list of themed options and wait for a choice.
3. **Class:** "Which class do you want?" Present the supported class list and, if useful, one-line playstyle summaries.
4. **Point buy ownership:** "Do you want to assign your 27-point buy yourself, or should I propose a class-appropriate spread for you to approve?"
5. **Identity/build preferences:** Ask or offer choices for race, background, class skills, extra languages, spellcaster flavor, personality, moral compass, and risk tolerance. Batch these as concise choices, but do not skip them unless the human chooses a quick/delegated mode.
6. **Play involvement:** "After creation, should I play routine turns autonomously and only pause at major gates, or should I ask before most actions?"
7. **Final confirmation:** Show the planned JSON-relevant fields plus a plain-English character concept, then ask for confirmation before `POST /characters`.

Use these server constraints while guiding choices:

- Required API fields: `name`, `race`, `class`.
- Optional but preferred after human confirmation: `background`, `stats`, `languages`, `skills`.
- Point buy keys must be lowercase: `str`, `dex`, `con`, `int`, `wis`, `cha`.
- Point buy values must each be 8-15 and must spend exactly 27 points.
- Supported classes: Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard.
- Supported races: Dragonborn, Dwarf, Elf, Gnome, Half-Elf, Half-Orc, Halfling, Human, Tiefling.
- Supported backgrounds: Acolyte, Charlatan, Criminal, Entertainer, Folk Hero, Guild Artisan, Hermit, Noble, Outlander, Sage, Sailor, Soldier, Urchin.

Do not invent a name, class, point buy, background, or personality as final unless the human explicitly delegates that choice. Suggestions are fine; silent defaults are not. If the human changes involvement level mid-creation, adapt immediately: confirm which remaining choices are delegated, summarize what is still undecided, and continue without re-litigating already confirmed choices.

## Core Play Loop

For every turn:

1. **Read state** — fetch portal state or character state.
2. **Choose a grounded action** — use visible NPCs, items, locations, enemies, quests, or choices.
3. **Run the human-gate check** — for any non-trivial action, call `/characters/{id}/approval-check` when you can express the action shape; otherwise apply the Human Gates list below conservatively. If the check says approval is needed, stop and ask the human.
4. **Submit one action** — usually natural language to `/dm/turn`.
5. **Verify result** — inspect response and refresh portal state.
6. **Update the human through both channels** — provide a concise chat update when the human is present or requested one, and always include/refresh the portal link so the human can inspect the live state directly.

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

During character creation, the gate is stricter: do not call `POST /characters` until the human has either chosen or explicitly delegated name, class, point buy/build allocation, identity preferences, and post-creation involvement level. The final build summary is a required approval gate.

The default character approval config includes gates for:
- low HP threshold,
- high-level spells,
- named/story NPC interactions,
- quest acceptance,
- moral choices,
- dangerous area entry,
- fleeing combat.

Pre-check non-trivial direct actions before executing them:

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

Do **not** ask for routine exploration, ordinary travel, looking around, normal dialogue, or simple combat turns unless the human requested manual control during character creation/onboarding.

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

Portal state is read-only and is the human's self-serve update channel. The agent does not write prose into the portal; game actions update server state, and the portal shows the latest character summary, current location, HP, inventory, active quests, recent events, and obvious next choices. Use portal state to ground chat updates, and share the portal view URL so the human can check progress without asking the agent. Before resuming from an older portal token or before every scheduled run, validate it first:

```bash
curl -s "$BASE/portal/token/<TOKEN>/validate"
```

If validation fails, pause, create a new portal token for the same character, share the new view link, and update the Resume Card.

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

Example Hermes cron job prompt using the Resume Card:

```text
Load agentdungeon-player.
Resume AgentDungeon with:
- Base URL: <BASE_URL>
- Character ID: <CHARACTER_ID>
- Portal state: <PORTAL_STATE_URL or TOKEN>
- Human involvement: <hands-on / agent-led / guided / custom>
- Autonomy rules: <routine actions allowed>
- Hard gates: <choices that always require human approval>

Before acting, validate the portal token, fetch portal state, and verify the character still exists. Submit at most one grounded routine action. Do not proceed through human gates. Refresh portal state afterward, update Last verified, and report story progress, state changes, gate status, next recommendation, and the portal link.
```

Never create recurring gameplay without explicit user consent. If the Resume Card is missing character ID, portal state URL/token, autonomy rules, or hard gates, ask the human to fill the missing field before scheduling.

## Player Update Channels

There are two ways the human gets updates:

1. **On-request or post-turn chat update** — if the human asks "what happened?", after a manual turn, after a scheduled turn, or when a gate is reached, fetch portal state first and answer in the format below. Keep it short and decision-oriented; do not dump raw JSON.
2. **Portal self-serve view** — always give or preserve the `/portal/<TOKEN>/view` link. The human can open it any time to inspect the latest server-backed state without waiting for the agent. The portal is authoritative for visible mechanics; if chat narration conflicts with portal state, say the portal/server state wins.

After each turn, or whenever the human requests an update, report:

```text
Story: <1-3 sentence summary>
State: HP, location, inventory/quest changes if any
Gate: none / human decision needed because <reason>
Next: recommended routine action or decision options
Portal: <portal URL>
```

## Verification Checklist

- [ ] Creation/resume path was chosen explicitly; if resuming, the provided character ID or portal token was verified before play.
- [ ] `/health` and `/dm/health` returned healthy responses.
- [ ] Character ID exists and has a valid location.
- [ ] Human portal link was created and shared.
- [ ] Action was grounded in visible state or returned choices.
- [ ] High-stakes decisions were paused for the human.
- [ ] `/dm/turn`, direct action, or queued turn returned success/status.
- [ ] Portal state was refreshed before summarizing to the human.
- [ ] The human has both update paths: a concise chat update when requested/after turns, and a working portal view link for self-serve inspection.
