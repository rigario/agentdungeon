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

Use this skill after a turn, before a recurring-turn report, or whenever the human asks "what happened?" The goal is to support two human update paths: (1) a concise agent-written chat update on request or after a turn, and (2) a portal link the human can open at any time for self-serve, server-backed state. Read the same state surface the human can see, distinguish story from mechanics, and produce a clear update without inventing facts.

Default public URL: `https://agentdungeon.com`

## When to Use

Use this skill when:
- the human asks for an update, status, recap, "what happened?", "where am I?", "what should I do next?", or similar,
- you have a portal URL/token and need the current game state,
- you need to summarize recent story progress for the human,
- a cron turn finished and needs a compact report,
- you need to compare DM response claims against current character/portal state,
- you need to remind the human that they can inspect the portal directly instead of waiting for a chat summary.

Do not use this skill to submit actions. Use `agentdungeon-player` for gameplay. Do not claim to have updated the portal manually: the portal is updated by server state changes from gameplay, not by the player agent writing summaries into it.

## Portal Inputs

A portal URL usually looks like:

```text
https://agentdungeon.com/portal/TOKEN/view
```

The token is the path segment after `/portal/` and before `/view` or `/state`. If the human pasted a full portal URL, extract that segment and never guess from memory. The machine-readable state endpoint is:

```text
https://agentdungeon.com/portal/TOKEN/state
```

## Read State

```bash
BASE=${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}
TOKEN='<TOKEN>'

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


## Resume Card Maintenance

When a report follows character creation, resume, or a recurring turn, preserve resumability. Include or update the Resume Card fields when available:

```text
Resume: <character name> (<character_id>)
Base: <actual BASE>
Portal: <portal view URL>
State: <portal state URL>
Human involvement: <stored setting or unknown>
Autonomy rules: <stored rule or ask human to confirm>
Hard gates: <stored gates or default high-stakes gates>
Last verified: <timestamp + HP/location/quest summary>
```

If the Resume Card is missing key fields, ask for the missing portal link or character ID before scheduling recurring play. Do not create recurring runs from a vague memory of the character.


## Two Player Update Paths

Always make both paths clear to the human:

1. **Ask-the-agent update** — when the human asks for a recap/status/next-step recommendation, fetch `/portal/{token}/state`, optionally cross-check character status, then summarize the state in chat.
2. **Look-at-the-portal update** — include the portal view URL in updates. Tell the human the portal is their always-on dashboard for character sheet, HP, location, inventory, quests, recent events, and visible next options.

The chat update should interpret and prioritize; the portal should be treated as the inspectable source of truth. If they differ, trust the portal/server fields and label narration-only claims as unconfirmed.

## Human Update Format

Use this default format:

```text
Story: <1-3 sentences on what just happened>
State: <HP, location, key items/quests/flags that changed>
Gate: <none OR decision needed + reason>
Next: <recommended safe action OR decision options>
Portal: <portal URL>
Resume: <character ID + last verified summary, when useful>
```

For a human-initiated "update me" request, use the same format but lead with current situation and next decision; do not take a new action unless the human also asked you to continue play.

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
5. Report state delta, gate status, next recommendation, and the portal view link so the human can inspect directly.

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
6. **Blurring the two update paths.** A chat summary is an agent explanation; the portal is a live state dashboard. Provide both, and do not imply the agent writes summaries into the portal unless the product adds that feature.

## Verification Checklist

- [ ] Portal token was parsed correctly.
- [ ] `/portal/{token}/state` returned successfully.
- [ ] State summary is grounded in returned fields.
- [ ] Any uncertainty is labeled clearly.
- [ ] Human gate status is explicit.
- [ ] Portal link is included in the final update.
- [ ] The update explicitly supports both player paths: ask the agent for a concise recap, or open the portal for live state.
