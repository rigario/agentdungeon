# AgentDungeon Play / Agent Quickstart

AgentDungeon is live at **https://agentdungeon.com**. Open the site to verify the game is live; the normal play loop is agent-led through the API while the human watches through a portal link.

The easiest way to play is to let an AI agent control a character while the human watches the portal and steps in for meaningful decisions.

## Prerequisites

You need an AI agent that can load Markdown skills and run web/API calls. Hermes users can install/load the skill with the commands below; if Hermes is not installed yet, follow the Hermes setup docs or run `hermes setup` first.

A **skill** is a Markdown instruction file that teaches the agent how to play AgentDungeon: when to ask you, how to create/resume a character, which endpoints to call, and how to report progress.

If you do not have an agent yet, you can still inspect the game with the API quickstart, but the intended hackathon experience is agent-led play.

## Human Quickstart

1. Open `https://agentdungeon.com` to confirm the game is reachable; you do not need to click through a full web UI to play.
2. Ask your agent to install/load the AgentDungeon player skill.
3. Let the agent create or resume a character.
4. Open the portal link the agent gives you. This is your always-on dashboard for character state, location, HP, inventory, quests, and recent events.
5. Ask the agent for a plain-English update whenever you want a recap or recommendation; otherwise, use the portal for self-serve state checks.
6. Step in only for high-stakes choices; let the agent handle routine exploration and combat.


If you are new, you do not need to know the rules. The agent should lead you through resume/new-character choice, character creation preferences, portal setup, and one safe first turn.

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

Sanity check after loading: ask the agent, "What game are we playing, and what should you ask me before creating a character?" It should answer AgentDungeon and mention resume-vs-new plus human-confirmed character creation.

For a named Hermes profile, replace `~/.hermes/skills` with `~/.hermes/profiles/<profile>/skills` and launch with `hermes -p <profile> -s agentdungeon-player`.

## Optional Skills

After the first successful turn, install optional support skills only if needed. Use raw Markdown URLs, not GitHub HTML pages:

```bash
mkdir -p ~/.hermes/skills/agentdungeon-portal-updates ~/.hermes/skills/agentdungeon-troubleshooting
curl -fsSL https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-portal-updates/SKILL.md \
  -o ~/.hermes/skills/agentdungeon-portal-updates/SKILL.md
curl -fsSL https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-troubleshooting/SKILL.md \
  -o ~/.hermes/skills/agentdungeon-troubleshooting/SKILL.md
```

Raw Markdown links:

- Required: https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-player/SKILL.md
- Portal updates: https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-portal-updates/SKILL.md
- Troubleshooting: https://raw.githubusercontent.com/rigario/agentdungeon/main/.hermes/skills/agentdungeon-troubleshooting/SKILL.md

DM-runtime/contributor instructions live separately under `.hermes/dm-skills/` and are not part of public player onboarding.

## Agent Onboarding Prompt

```text
Play AgentDungeon at https://agentdungeon.com.

Run the onboarding flow:
1. Ask whether to resume an existing character or create a new one.
2. For resume: request the character ID or portal link, verify state, produce a Resume Card, then continue play.
3. For new character: complete the human-involved creation flow before `POST /characters`.
4. Create or refresh a human portal link and share it.
5. Take one grounded first turn only after creation/resume state is verified.
6. Summarize story, character state, resume details, gate status, and the next recommended action. Explain that the player has two update paths: ask the agent for a concise recap, or open the portal link for live state.

Play autonomously for routine exploration, normal dialogue, travel, and simple combat. Ask me only before irreversible or high-stakes decisions.
```


The agent should produce a Resume Card after setup so the same character can be continued later or used in a recurring play schedule. Save it somewhere you can paste into a future agent session.

Example Resume Card:

```text
AgentDungeon Resume Card
Base URL: https://agentdungeon.com
Character ID: <character_id>
Character name: <name>
Portal view: https://agentdungeon.com/portal/<TOKEN>/view
Portal state: https://agentdungeon.com/portal/<TOKEN>/state
Human involvement: guided quick build + agent-led routine play
Autonomy rules: routine exploration, normal dialogue, safe travel, and simple combat allowed
Hard gates: major quests, moral choices, named non-hostile NPC attacks, rare resources, dangerous areas, death risk
Last verified: <timestamp> — HP/location/quest summary
```

## Player Updates

AgentDungeon should support two player update paths:

1. **Ask the agent:** The player can ask "what happened?", "where am I?", "what changed?", or "what should I do next?" The agent should refresh portal state first, then answer with Story / State / Gate / Next / Portal.
2. **Look at the portal:** The player can open `/portal/<TOKEN>/view` any time to inspect live server-backed state. The portal is the self-serve dashboard; the agent's chat update is the interpretation/recommendation layer.

If the portal state and chat narration disagree, treat the portal/server state as authoritative.

## Live Loop

1. Health check `https://agentdungeon.com/health` and `/dm/health`.
2. Create a character or use a provided `character_id`.
3. Create a portal token and give the human `/portal/<TOKEN>/view`.
4. Use `/dm/turn` for natural language play.
5. Refresh `/portal/<TOKEN>/state` after turns.
6. Give a concise chat update after turns or on request, and include the portal link so the human can inspect directly.
7. Ask the human only for irreversible or high-stakes decisions.

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

During character creation, the human should choose or explicitly delegate name, class, race, background, point-buy/stat spread, personality/risk tolerance, and how often the agent should pause. The agent must summarize the final build and get approval before creating the character.

During play, ask the human before:

- accepting/refusing major quests,
- making moral or ending choices,
- attacking named non-hostile NPCs,
- using rare/limited resources,
- entering obvious death-risk situations,
- continuing through likely death.

Everything else can be agent-owned.

## Optional Recurring Gameplay

After one successful manual turn, the agent may offer a recurring schedule such as every 30-60 minutes. Each scheduled run should submit at most one grounded routine action, stop at human gates, refresh portal state, and report story/state changes with the portal link. Never create recurring gameplay without explicit human consent.

Use the Resume Card as the entire prompt/context for recurring play; do not rely on chat history. A safe recurring prompt is:

```text
Load agentdungeon-player. Resume AgentDungeon using this Resume Card: <paste card>. Validate the portal token, fetch portal state, submit at most one grounded routine action, stop at human gates, refresh state, and report Story / State / Gate / Next / Portal.
```

If the agent cannot validate the portal token, cannot fetch state, or the next action hits a human gate, it should pause and ask rather than improvising.

## Human Override

If the agent seems wrong, tell it to stop and paste the latest portal link/state. The agent should refresh state, explain what is confirmed versus uncertain, and propose a correction. Do not let it continue through a high-stakes gate just to keep the schedule moving.
