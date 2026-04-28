---
title: Hackathon Submission
created: 2026-04-20
---

# Hackathon Submission — The Dreaming Hunger

## Entry Requirements
- Tweet demo video tagging @NousResearch
- Deadline: May 3, 2026
- Prize: $25k (Hermes Agent Creative Hackathon)
- Live demo: https://agentdungeon.com
- Public repo: https://github.com/rigario/projectd20
- Public docs: `docs/index.md`

## Twitter/X Thread

**Tweet 1 (Hook + Video):**
We built an RPG where your AI agent is the DM — and it never forgets what you did.

The Dreaming Hunger: a persistent D&D campaign where your character can be possessed, marked, and hunted by an ancient entity.

Built entirely with @NousResearch Hermes Agent 🎲🧵

**Tweet 2 (Story):**
Your character enters Thornhold, a dying town on the edge of Whisperwood.

A betrayer named Del lures you to a cursed ruin. You're marked with an ancient sigil — the Mark of the Dreamer.

Every choice advances a living narrative. Your agent tracks 8 grim portents in real-time.

**Tweet 3 (Differentiator):**
Other hackathon entries built tools. We built a *world*.

• 9 locations, 8 NPCs, 10 handcrafted encounters
• Full D&D 5E SRD combat engine
• Persistent character state across sessions
• A Fronts system that advances while you sleep

**Tweet 4 (Auth):**
Human-centric auth with agent delegation:

→ User logs in via Gmail/X OAuth
→ Registers an AI agent (Ed25519 key pair)
→ Agent plays the game on user's behalf
→ Lost your keys? Social recovery via OAuth

Characters belong to humans. Agents operate them.

**Tweet 5 (Tech Stack):**
• Hermes Agent (Nous Research) — orchestration + persistent memory
• FastAPI + SQLite (WAL mode) — game server
• Ed25519 challenge-response — agent authentication
• 56 REST endpoints — full game API
• Jinja2 dark-fantasy UI — character sheets, maps, lore viewer

**Tweet 6 (Behind the Scenes):**
The narrative engine uses three layers:

1. Server validates rules (combat, saves, flags)
2. DM Agent narrates, advances fronts, triggers events
3. Player Agent submits actions on behalf of humans

The Mark of the Dreamer has 4 stages. Fail your WIS save, and you lose yourself.

**Tweet 7 (CTA):**
Try it: the game runs on a single FastAPI server with zero infrastructure.

Star the repo. Play the campaign. See if your agent can survive the Dreaming Hunger.

Built for the @NousResearch Hermes Agent Creative Hackathon 🏆

## Video Script (2 min)

| Time | Scene |
|------|-------|
| 0:00 | Hook — "An agent-driven RPG where your character can be possessed" |
| 0:10 | Character creation — visual sheet renders |
| 0:25 | Map of Thornhold — 9 locations |
| 0:35 | The Rusty Tankard — meet Del |
| 0:50 | Betrayal — WIS save, Mark applied |
| 1:05 | Character sheet — Mark of Dreamer Stage 1 |
| 1:15 | Lore viewer — inspect the Mark |
| 1:25 | Fronts panel — grim portents advancing |
| 1:40 | "Your agent plays while you sleep" |
| 1:55 | CTA — "Built with Hermes Agent" |

## Recording Checklist
- [ ] Screen record demo page at localhost:8600/demo
- [ ] 1080p resolution
- [ ] One-take recording, edit later
- [ ] Post tweet with video, tag @NousResearch
