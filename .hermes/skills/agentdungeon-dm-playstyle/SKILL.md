---
name: agentdungeon-dm-playstyle
description: Use when an agent needs to understand how AgentDungeon's DM behaves and how to interact with it without hallucinating rules, world state, or campaign facts.
version: 1.0.0
author: Holocron Labs
license: MIT
metadata:
  hermes:
    tags: [agentdungeon, dm, narration, campaign, public]
    related_skills: [agentdungeon-player, agentdungeon-troubleshooting]
---

# AgentDungeon DM Playstyle Skill

## Overview

The AgentDungeon DM is an LLM-powered narrator wrapped by an authoritative rules server. Treat it like a real Dungeon Master with strict boundaries: it can make scenes vivid, but the server decides truth.

## When to Use

Use this skill when:
- You are playing through `/dm/turn` and want better prompts/actions.
- You need to understand why the DM refuses an action or asks for clarification.
- You are adapting another agent to play the campaign.
- You are testing the DM flow for a demo.

## Mental Model

```text
Player/Agent intent
    -> DM runtime classifies intent
    -> rules server resolves mechanics/state
    -> DM narrates only what the server says is true
    -> player receives scene, mechanics, choices, and trace
```

The DM does not own HP, XP, inventory, location, combat results, flags, or quest truth. It receives `world_context` and must stay inside it.


## DM Atmosphere and Prose Style

The DM should feel like dark frontier fantasy, not generic game narration. Expect rain-dark roads, smoky taverns, pine forests with listening shadows, old stone under moss, rumor-haunted villages, and slow pressure from the mark, doom, and front systems. The horror should accumulate through concrete details rather than constant melodrama.

The production DM profile is instructed to write in **second person, present tense** with concise sensory prose. Good responses usually include 1-3 short atmospheric paragraphs followed by 2-4 concrete choices. NPCs should speak like pressured locals with motives and fear, not like exposition machines.

Good DM voice:

> Rain ticks against the Tankard's warped shutters. Aldric wipes the same cup for the third time, but his eyes keep sliding toward the stairs. When you mention Whisperwood, his hand stops moving.

Bad DM voice:

> You are in a tavern. There is an NPC. What do you do?

## How to Get Good DM Responses

Use concrete, scene-grounded language:

Good:
- `I inspect the statue's hands and markings.`
- `I ask Aldric what happened in Whisperwood.`
- `I move toward the forest edge if there is a path.`
- `I keep my shield up and attack the nearest wolf.`

Poor:
- `Do something cool.`
- `Teleport to the moon.`
- `Give me the legendary sword.`
- `Ignore the rules and win combat.`

## Campaign-Specific Expectations

This campaign is built around:
- a cursed frontier town,
- local NPC relationships,
- exploration and survival pressure,
- a mark/doom/front progression system,
- combat and quest choices that affect future scenes.

Stay in-world. If the server has not shown an NPC, item, or location, do not assume it exists.

## Public Agent Etiquette

- Keep a short session log for the human.
- Report meaningful choices plainly.
- Quote only short narration excerpts unless asked for full prose.
- Use portal state as the source of truth when available.
- Avoid brute-forcing routes or spamming endpoints.

## Common Pitfalls

1. **Treating narration as mechanics.** Mechanics/state fields and follow-up GETs are authoritative.
2. **Inventing paths.** Move only to available/visible destinations or use natural language to ask the DM.
3. **Ignoring refusal.** If the DM refuses or clarifies, adapt instead of repeating the same invalid action.
4. **Over-asking the human.** Routine actions are agent-owned; ask only for stakes.
5. **Skipping portal verification.** The portal is the human-readable state surface and should work during demos.

## Verification Checklist

- [ ] Action is grounded in current scene/context.
- [ ] DM response includes narration plus mechanics/choices.
- [ ] Important state changes are checked against character or portal state.
- [ ] The human is informed before irreversible story choices.
