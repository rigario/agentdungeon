---
name: agentdungeon-troubleshooting
description: Use when AgentDungeon public play, portal access, DM turns, or local smoke checks fail. Provides safe diagnostics without requiring internal production access.
version: 1.0.0
author: Holocron Labs
license: MIT
metadata:
  hermes:
    tags: [agentdungeon, troubleshooting, smoke, public]
    related_skills: [agentdungeon-player]
---

# AgentDungeon Troubleshooting Skill

## Overview

This skill helps public users and agents diagnose the live AgentDungeon game without needing private deployment access.

Default public URL: `https://agentdungeon.com`. For self-hosted installs, replace it with your deployment URL.

## Quick Health Checks

```bash
curl -s ${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}/health
curl -s ${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}/dm/health
curl -s ${AGENTDUNGEON_BASE_URL:-https://agentdungeon.com}/api/map/data
```

Expected:
- `/health` returns 200 with rules-server health.
- `/dm/health` returns 200 and reports the DM runtime ready.
- `/api/map/data` returns locations and connectivity data.

## Minimal Public Smoke Flow

```bash
CHAR_ID=$(curl -s -X POST https://agentdungeon.com/characters   -H 'Content-Type: application/json'   -d '{"name":"SmokeAgent","race":"Human","class":"Fighter","background":"Soldier"}'   | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

curl -s -X POST https://agentdungeon.com/dm/turn   -H 'Content-Type: application/json'   -d "{"character_id":"$CHAR_ID","message":"I look around and ask who needs help."}"

curl -s -X POST https://agentdungeon.com/portal/token   -H 'Content-Type: application/json'   -d "{"character_id":"$CHAR_ID"}"
```

## Diagnosis Table

| Symptom | Likely cause | Safe next step |
|---|---|---|
| `/health` fails | rules server unavailable | wait/retry; report endpoint/status |
| `/dm/health` fails | DM runtime unavailable | play via direct actions or report status |
| `/dm/turn` times out | narrator/provider latency | retry once; compare against tick budget |
| DM refuses action | invalid/off-world intent | rephrase grounded in scene |
| Portal token works but page blank | frontend/static issue | fetch `/portal/<token>/state` and report status |
| Move fails | destination unavailable | inspect current choices or map data |

## What to Report

When filing an issue, include:
- timestamp,
- endpoint,
- HTTP status,
- character ID if created,
- short response excerpt,
- exact player message/action.

Do not include API keys, cookies, private tokens, or screenshots containing unrelated personal data.

## Verification Checklist

- [ ] Health endpoints checked first.
- [ ] Failure reproduced once after a short retry.
- [ ] Character ID and endpoint/status captured.
- [ ] No secrets included in report.
