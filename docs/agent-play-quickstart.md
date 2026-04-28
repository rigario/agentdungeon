# AgentDungeon Play / Agent Quickstart

AgentDungeon is live at **https://agentdungeon.com**.

The easiest way to play is to let an AI agent control a character while the human makes high-stakes decisions.

## Human Quickstart

1. Open `https://agentdungeon.com`.
2. Create or receive a character portal link.
3. Watch state, inventory, map, and recent actions in the portal.
4. Step in for major choices; let the agent handle routine exploration and combat turns.

## Agent Quickstart

Load the public skills from this repo:

```text
.hermes/skills/agentdungeon-player/SKILL.md
.hermes/skills/agentdungeon-dm-playstyle/SKILL.md
.hermes/skills/agentdungeon-troubleshooting/SKILL.md
```

Then follow the live loop:

1. Health check `https://agentdungeon.com/health` and `/dm/health`.
2. Create a character or use a provided `character_id`.
3. Use `/dm/turn` for natural language play.
4. Use `/portal/token` to generate a human-readable portal.
5. Ask the human only for irreversible or high-stakes decisions.

## Core Action Grammar

Natural language examples:

```text
I look around the tavern.
I ask Aldric what happened in Whisperwood.
I inspect the statue carefully.
I move toward the forest edge if a path is available.
I attack the wolf with my longsword.
I rest if the area is safe.
```

Direct action examples:

```json
{"action_type":"look"}
{"action_type":"explore"}
{"action_type":"interact", "target":"Aldric"}
{"action_type":"move", "target":"forest-edge"}
{"action_type":"attack", "target":"wolf"}
{"action_type":"rest"}
```

## What the Human Should Decide

Ask the human before:

- accepting/refusing major quests,
- attacking named non-hostile NPCs,
- using rare/limited resources,
- choosing an ending,
- continuing through likely death.

Everything else can be agent-owned.
