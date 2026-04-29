---
name: agentdungeon-portal-updates
description: Use when an AgentDungeon player agent needs to read portal/server state and produce concise story/state updates for the human player between turns.
version: 1.0.0
author: Holocron Labs
license: MIT
metadata:
  hermes:
    tags: [agentdungeon, portal, state, human-update, gameplay]
    related_skills: [agentdungeon-player, agentdungeon-troubleshooting]
---

# AgentDungeon Portal Updates Skill

## Overview

Use this skill after a turn, before a recurring-turn report, or whenever the human asks "what happened?" The goal is to read the same state surface the human can see, distinguish story from mechanics, and produce a clear update without inventing facts.

Default public URL: `https://agentdungeon.com`

## When to Use

Use this skill when:
- you have a portal URL/token and need the current game state,
- you need to summarize recent story progress for the human,
- a cron turn finished and needs a compact report,
- you need to compare DM response claims against current character/portal state.

Do not use this skill to submit actions. Use `agentdungeon-player` for gameplay.

## Portal Inputs

A portal URL usually looks like:

```text
https://agentdungeon.com/portal/TOKEN/view
```

The token is the path segment after `/portal/` and before `/view`. The machine-readable state endpoint is:

```text
https://agentdungeon.com/portal/TOKEN/state
```

## Read State

```bash
BASE=${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}
TOKEN=<TOKEN>

curl -s "$BASE/portal/$TOKEN/state"
```

If you know the character ID too, cross-check lightweight status when useful:

```bash
curl -s "$BASE/characters/$CHARACTER_ID/status"
curl -s "$BASE/characters/$CHARACTER_ID"
```

Use `/api/map/data` only when route/location context matters:

```bash
curl -s "$BASE/api/map/data"
```

## What to Extract

Look for:
- character name, race/class/level,
- current HP and conditions,
- current location and visible connections,
- active quests/objectives,
- inventory/key item changes,
- recent events/action log,
- doom/front/pressure indicators if present,
- token validity or portal errors.

Treat explicit state fields as authoritative. If narration says something but state does not confirm it, phrase it as narration only, not as a confirmed mechanical change.

## Human Update Format

Use this default format:

```text
Story: <1-3 sentences on what just happened>
State: <HP, location, key items/quests/flags that changed>
Gate: <none OR decision needed + reason>
Next: <recommended safe action OR decision options>
Portal: <portal URL>
```

For short chat surfaces, compress to:

```text
<Story sentence> State: <HP/location/change>. Next: <action/question>. Portal: <url>
```

## Gate Language

If a human decision is needed, be explicit and non-leading:

```text
Gate: Decision needed — accepting Aldric's quest may commit the character to the Whisperwood arc. Options: accept, refuse, ask for more information, or delay.
```

Do not hide risk. Do not continue through a gate just because the next action seems obvious.

## Cron / Recurring Turn Reports

For recurring play, each run should:

1. Fetch portal state before acting if possible.
2. Submit at most one grounded routine turn via `agentdungeon-player`.
3. Poll any returned `status_url` if using queued turns.
4. Fetch portal state again.
5. Report state delta, gate status, and next recommendation.

Recommended report:

```text
Turn complete.
Story: ...
Changed: location/inventory/quest/HP changes or "no confirmed state change".
Gate: none / human input needed.
Next scheduled action: ... / paused until you decide.
Portal: ...
```

## Common Pitfalls

1. **Summarizing from memory.** Always refresh portal state before reporting if a token is available.
2. **Confusing prose with mechanics.** Mechanics/state fields win over atmospheric narration.
3. **Over-reporting raw JSON.** The human wants story + state + next decision, not endpoint dumps.
4. **Continuing through gates.** A good update pauses cleanly when stakes rise.
5. **Losing the portal URL.** Include the portal link in recurring reports so the human can inspect directly.

## Verification Checklist

- [ ] Portal token was parsed correctly.
- [ ] `/portal/{token}/state` returned successfully.
- [ ] State summary is grounded in returned fields.
- [ ] Any uncertainty is labeled clearly.
- [ ] Human gate status is explicit.
- [ ] Portal link is included in the final update.
