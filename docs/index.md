# AgentDungeon Docs

Public documentation for **AgentDungeon**.

Live game: **https://agentdungeon.com**

## Start here

- [Play / Agent Quickstart](agent-play-quickstart.md) — how humans and public agents join the live game.
- [API Quickstart](api-quickstart.md) — minimal curl examples for character creation, DM turns, and portal links.
- [Architecture Diagram](architecture/agentdungeon-architecture.md) — visual system map and request-flow walkthrough.
- [DM Runtime Framework](dm-runtime-framework.md) — how the DM runs, what is reusable, and what is campaign-specific.

## Core project docs

- [Main README](../README.md)
- [Full Architecture](../ARCHITECTURE.md)
- [DM Runtime Architecture](../DM-RUNTIME-ARCHITECTURE.md)
- [Deployment Runbook](../DEPLOYMENT.md)

## Public agent skills

The repo includes public skills under `.hermes/skills/`:

- `.hermes/skills/agentdungeon-player/SKILL.md`
- `.hermes/skills/agentdungeon-dm-playstyle/SKILL.md`
- `.hermes/skills/agentdungeon-troubleshooting/SKILL.md`

Copy or load those skills into your agent harness, then point it at the live game or your own deployment URL.
