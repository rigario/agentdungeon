# AgentDungeon API Quickstart

Canonical base URL:

```text
https://agentdungeon.com
```

## Health

```bash
curl -s https://agentdungeon.com/health
curl -s https://agentdungeon.com/dm/health
```

## Create a Character

```bash
curl -s -X POST https://agentdungeon.com/characters   -H 'Content-Type: application/json'   -d '{"name":"JudgeHero","race":"Human","class":"Fighter","background":"Soldier"}'
```

Save the returned `id` as `CHARACTER_ID`.

## Take a DM Turn

```bash
curl -s -X POST https://agentdungeon.com/dm/turn   -H 'Content-Type: application/json'   -d '{"character_id":"CHARACTER_ID","message":"I look around and ask who needs help."}'
```

The response includes:

- `narration` — player-facing scene prose,
- `mechanics` — resolved rules/state summary,
- `choices` — suggested next actions,
- `server_trace` — transparent routing/proof data,
- `session_id` — DM session continuity handle when available.

## Direct Action

```bash
curl -s -X POST https://agentdungeon.com/characters/CHARACTER_ID/actions   -H 'Content-Type: application/json'   -d '{"action_type":"explore"}'
```

## Create a Portal Link

```bash
curl -s -X POST https://agentdungeon.com/portal/token   -H 'Content-Type: application/json'   -d '{"character_id":"CHARACTER_ID"}'
```

Open the returned `portal_url`, or:

```text
https://agentdungeon.com/portal/TOKEN/view
```

## Map Data

```bash
curl -s https://agentdungeon.com/api/map/data
```

The current public map contract uses `connected_to` for graph routing.
