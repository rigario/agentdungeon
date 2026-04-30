# AgentDungeon API Quickstart

Canonical base URL:

```text
https://agentdungeon.com
```

This page is for API smoke tests and manual debugging. For normal public play, load `.hermes/skills/agentdungeon-player/SKILL.md` and let the agent lead the human through resume/new-character choice and human-confirmed character creation. Do not use these examples to silently create a generic player character for someone.

## Health

```bash
BASE=${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}
curl -s "$BASE/health"
curl -s "$BASE/dm/health"
```

## Create a Character

Use confirmed human choices. Required fields are `name`, `race`, and `class`; `background` and `stats` are strongly recommended after the human confirms or delegates them.

Supported races: Dragonborn, Dwarf, Elf, Gnome, Half-Elf, Half-Orc, Halfling, Human, Tiefling.
Supported classes: Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard.

```bash
BASE=${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}
curl -s -X POST "$BASE/characters" \
  -H 'Content-Type: application/json' \
  -d '{"name":"<HUMAN_CHOSEN_NAME>","race":"<CONFIRMED_RACE>","class":"<CONFIRMED_CLASS>","background":"<CONFIRMED_BACKGROUND>","stats":{"str":15,"dex":14,"con":13,"int":10,"wis":12,"cha":8}}'
```

Save the returned `id` as `CHARACTER_ID`.

## Resume Existing Character

From a character ID:

```bash
CHARACTER_ID='<KNOWN_CHARACTER_ID>'
curl -s "$BASE/characters/$CHARACTER_ID/status"
curl -s "$BASE/characters/$CHARACTER_ID"
```

From a portal token:

```bash
TOKEN='<TOKEN>'
curl -s "$BASE/portal/token/$TOKEN/validate"
curl -s "$BASE/portal/$TOKEN/state"
```

## Take a DM Turn

```bash
CHARACTER_ID='<CHARACTER_ID>'
curl -s -X POST "$BASE/dm/turn" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","message":"I look around and ask who needs help."}' "$CHARACTER_ID")"
```

The response includes:

- `narration` — player-facing scene prose,
- `mechanics` — resolved rules/state summary,
- `choices` — suggested next actions,
- `server_trace` — transparent routing/proof data,
- `session_id` — DM session continuity handle when available.

## Direct Action

```bash
CHARACTER_ID='<CHARACTER_ID>'
curl -s -X POST "$BASE/characters/$CHARACTER_ID/actions" \
  -H 'Content-Type: application/json' \
  -d '{"action_type":"explore"}'
```

## Human Gate Pre-Check

Use this before non-trivial direct actions when you can express the action shape. If the response says approval is needed, stop and ask the human.

```bash
curl -s -X POST "$BASE/characters/$CHARACTER_ID/approval-check" \
  -H 'Content-Type: application/json' \
  -d '{"action_type":"move","target":"whisperwood"}'
```

## Create a Portal Link

```bash
curl -s -X POST "$BASE/portal/token" \
  -H 'Content-Type: application/json' \
  --data "$(printf '{"character_id":"%s","label":"Human watch link"}' "$CHARACTER_ID")"
```

Open the returned `portal_url`, or:

```text
https://agentdungeon.com/portal/<TOKEN>/view
```

Machine-readable state:

```bash
TOKEN='<TOKEN>'
curl -s "$BASE/portal/$TOKEN/state"
```

## Map Data

```bash
curl -s "$BASE/api/map/data"
```

The current public map contract uses `connected_to` for graph routing.

## Error Handling

- If `/health` or `/dm/health` fails, stop and report the endpoint/status instead of creating characters.
- If `POST /characters` returns 400, check supported race/class/background names and point-buy values.
- If `/dm/turn` times out, retry once, then check `/dm/health`; do not spam turns.
- If portal token validation fails, create a new portal token for the same character and update the Resume Card.
- If an action response conflicts with portal state, treat portal/server state as authoritative and label narration-only claims clearly.
