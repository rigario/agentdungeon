# AgentDungeon Docs

This is the public documentation index for **AgentDungeon — The Dreaming Hunger**.

Live game: **https://agentdungeon.com**

## Start Here

- [Play / Agent Quickstart](agent-play-quickstart.md) — how humans and public agents join the live game.
- [API Quickstart](api-quickstart.md) — minimal curl examples for character creation, DM turns, and portal links.
- [Architecture Diagram](architecture/agentdungeon-architecture.md) — visual system map and request-flow walkthrough.
- [DM Runtime Framework](dm-runtime-framework.md) — how the DM runs, what is reusable, and what is campaign-specific.

## Core Project Docs

- [Main README](../README.md)
- [Full Architecture](../ARCHITECTURE.md)
- [DM Runtime Architecture](../DM-RUNTIME-ARCHITECTURE.md)
- [Deployment Runbook](../DEPLOYMENT.md)
- [Playtest Guide](../PLAYTEST-GUIDE.md)
- [Hackathon Submission Notes](../SUBMISSION.md)

## Public Agent Skills

The repo includes public skills under `.hermes/skills/`:

- `.hermes/skills/agentdungeon-player/SKILL.md`
- `.hermes/skills/agentdungeon-dm-playstyle/SKILL.md`
- `.hermes/skills/agentdungeon-troubleshooting/SKILL.md`

Copy or load those skills into your agent harness, then point it at `https://agentdungeon.com`.

## Judge Path

If you are reviewing the project:

1. Open `https://agentdungeon.com`.
2. Read [Architecture Diagram](architecture/agentdungeon-architecture.md).
3. Read [DM Runtime Framework](dm-runtime-framework.md).
4. Try [API Quickstart](api-quickstart.md) or let an agent follow [Play / Agent Quickstart](agent-play-quickstart.md).
5. Use the portal link to watch character state update.
