# AgentDungeon Play / Agent Quickstart

AgentDungeon is live at **https://agentdungeon.com**.

The easiest way to play is to let an AI agent control a character while the human watches the portal and steps in for meaningful decisions.

## Human Quickstart

1. Open `https://agentdungeon.com`.
2. Ask your agent to install/load the AgentDungeon player skill.
3. Let the agent create or resume a character.
4. Open the portal link the agent gives you.
5. Step in only for high-stakes choices; let the agent handle routine exploration and combat.

## Minimal Agent Skill Install

The player agent does **not** need to clone the whole repo.

Install only the required player skill:

```bash
mkdir -p ~/.hermes/skills/agentdungeon-player
curl -fsSL   https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-player/SKILL.md   -o ~/.hermes/skills/agentdungeon-player/SKILL.md
```

Then start Hermes with the skill:

```bash
hermes -s agentdungeon-player
```

For a named Hermes profile, replace `~/.hermes/skills` with `~/.hermes/profiles/<profile>/skills` and launch with `hermes -p <profile> -s agentdungeon-player`.

## Optional Skills

After the first successful turn, install optional support skills only if needed:

```text
.hermes/skills/agentdungeon-portal-updates/SKILL.md      # human-facing portal/story updates
.hermes/skills/agentdungeon-troubleshooting/SKILL.md     # diagnostics when play or portal access fails
```

DM-runtime/contributor instructions live separately under `.hermes/dm-skills/` and are not part of public player onboarding.

## Agent Onboarding Prompt

```text
Play AgentDungeon at https://agentdungeon.com.

Run the onboarding flow:
1. Health check the game and DM runtime.
2. Create a new character.
3. Create a human portal link and show it to me.
4. Take one grounded first turn.
5. Summarize story, character state, gate status, and the next recommended action.

Play autonomously for routine exploration, normal dialogue, travel, and simple combat. Ask me only before irreversible or high-stakes decisions.
```

## Live Loop

1. Health check `https://agentdungeon.com/health` and `/dm/health`.
2. Create a character or use a provided `character_id`.
3. Create a portal token and give the human `/portal/<TOKEN>/view`.
4. Use `/dm/turn` for natural language play.
5. Refresh `/portal/<TOKEN>/state` after turns.
6. Ask the human only for irreversible or high-stakes decisions.

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
- making moral or ending choices,
- attacking named non-hostile NPCs,
- using rare/limited resources,
- entering obvious death-risk situations,
- continuing through likely death.

Everything else can be agent-owned.

## Optional Recurring Gameplay

After one successful manual turn, the agent may offer a recurring schedule such as every 30-60 minutes. Each scheduled run should submit at most one grounded routine action, stop at human gates, refresh portal state, and report story/state changes with the portal link. Never create recurring gameplay without explicit human consent.
