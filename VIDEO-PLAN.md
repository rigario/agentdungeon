# D20 Hackathon Video — Production Plan

> **Deadline:** May 3, 2026
> **Format:** 90-120 second demo video for Twitter/X
> **Entry:** Tweet tagging @NousResearch (Hermes Agent Creative Hackathon)
> **Prize:** $25k

---

## Strategy

The video needs to do ONE thing well: make judges feel like they're watching
a living world driven by agents, not a static demo.

### What Wins Hackathon Videos
1. Hook in first 3 seconds (not 10 — THREE)
2. Show, don't narrate
3. Demonstrate the Hermes Agent integration clearly
4. Visual polish = perceived quality
5. Under 90 seconds (Twitter autoplay sweet spot)
6. Clear "I want to try this" feeling at the end

### What Makes D20 Different From Other Entries
- Other entries built tools. We built a WORLD.
- The DM agent narrates in real-time with Kimi k2.5
- Characters persist across sessions — your choices MATTER
- The Mark of the Dreamer is a mechanic that exists BECAUSE agents can track state
- Pixel art aesthetic reads immediately as "this is a game" not "this is a demo"

---

## Video Structure (90 seconds)

### Scene 1 — HOOK (0:00-0:05)
**Visual:** Dark screen, pixel art of the Dreaming Hunger entity fades in.
**Text overlay:** "Your AI agent is the DM. It never forgets."
**Audio:** Ambient.mp3 starts low.
**WHY:** Judges see hundreds of demos. You have 3 seconds.

### Scene 2 — THE WORLD (0:05-0:15)
**Visual:** Pan across the Thornhold map (9 locations, pixel art).
**Action:** Click through 3-4 locations showing the pixel art renders.
**Text overlay:** "9 locations. 8 NPCs. A living world."
**WHY:** Instantly communicates scope and visual quality.

### Scene 3 — CHARACTER CREATION (0:15-0:25)
**Visual:** Create a new character via the demo page.
**Action:** Show the character sheet rendering — stats, class, race.
**Text overlay:** "Full D&D 5E SRD. Server-side persistence."
**WHY:** Shows it's a real system, not a mockup.

### Scene 4 — THE ENCOUNTER (0:25-0:40)
**Visual:** Enter the Rusty Tankard. Meet Del.
**Action:** Type a message to Del. DM agent narrates the response in real-time.
**Text overlay:** "The DM narrates. The world responds."
**WHY:** This is the "wow" moment — the agent is the DM, narrating live.

### Scene 5 — THE BETRAYAL (0:40-0:55)
**Visual:** Del leads you to the ruin. WIS save. Mark applied.
**Action:** Show the combat/resolution. Character sheet updates with Mark of Dreamer.
**Text overlay:** "Fail your save. Lose yourself."
**WHY:** This is the narrative hook. The Mark is a mechanic that ONLY works because agents track state.

### Scene 6 — THE SYSTEM (0:55-1:10)
**Visual:** Split screen — left shows character sheet, right shows lore viewer.
**Action:** Inspect the Mark. Read the dark history. Show the Fronts panel with grim portents advancing.
**Text overlay:** "The Fronts system advances while you sleep."
**WHY:** Shows depth. This isn't a toy — it's a persistent world.

### Scene 7 — THE AGENT (1:10-1:20)
**Visual:** Show the DM runtime health endpoint. Show the agent auth system.
**Text overlay:** "Ed25519 agent auth. Characters belong to humans. Agents operate them."
**WHY:** Technical credibility. Shows this is built on Hermes Agent properly.

### Scene 8 — CTA (1:20-1:30)
**Visual:** The Dreaming Hunger pixel art. Logo.
**Text:** "Built with Hermes Agent. The DM that never sleeps."
**Tag:** @NousResearch
**WHY:** Clean ending. Memorable line.

---

## Recording Setup

### Technical
- **Resolution:** 1920x1080 (landscape for Twitter video)
- **Browser:** Full-screen Chrome, dark theme
- **Server:** agentdungeon.com (live)
- **Screen recorder:** OBS or built-in (whatever's available)
- **Audio:** ambient.mp3 (already in the project) as background

### Pre-Recording Checklist
1. [ ] Server live and healthy (DM runtime + rules server)
2. [ ] Create a fresh demo character (not one of the test characters)
3. [ ] Navigate through the demo flow once to confirm no errors
4. [ ] Close all browser tabs except the demo
5. [ ] Clean browser bookmarks bar
6. [ ] Set browser zoom to 100%
7. [ ] ambient.mp3 loaded as background audio

### Demo Flow (what to actually do on camera)
1. Open /demo page
2. Create character → show sheet
3. Click map → navigate to Rusty Tankard
4. Talk to Del → show DM narration
5. Follow Del to ruin → WIS save → Mark applied
6. Open character sheet → show Mark of Dreamer
7. Open lore viewer → inspect Mark
8. Open map → show Fronts advancing
9. Cut to CTA

---

## Post-Production

### Editing
- Trim dead air between actions
- Add text overlays (white, subtle shadow, bottom third)
- Add subtle crossfade between scenes
- Background music: ambient.mp3 (royalty-free, from project)
- Total length: 90 seconds max

### Tools
- DaVinci Resolve (free) or iMovie
- No fancy effects needed — clean cuts, readable text

### Export
- 1080p H.264
- Under 50MB for Twitter upload
- MP4 format

---

## Twitter Thread (Post With Video)

**Tweet 1 (video attached):**
We built an RPG where your AI agent is the DM — and it never forgets what you did.

The Dreaming Hunger: a persistent D&D campaign where your character can be possessed, marked, and hunted by an ancient entity.

Built entirely with @NousResearch Hermes Agent

**Tweet 2:**
Other hackathon entries built tools. We built a world.

- 9 locations, 8 NPCs, 10 encounters
- Full D&D 5E SRD combat engine
- Persistent character state across sessions
- A Fronts system that advances while you sleep

**Tweet 3:**
The DM agent narrates in real-time using Kimi k2.5.
The Mark of the Dreamer has 4 stages. Fail your WIS save, and you lose yourself.

Characters belong to humans. Agents operate them.

**Tweet 4:**
56 REST endpoints. Ed25519 agent auth. SQLite with WAL mode.
Zero infrastructure — runs on a single FastAPI server.

The DM that never sleeps.

---

## Timeline

| Date | Task |
|------|------|
| Apr 23 | Finalize script, prep demo flow |
| Apr 24 | Record video |
| Apr 25 | Edit + export |
| Apr 26 | Post tweet thread + video |
| Apr 27-30 | Monitor engagement, respond |
| May 3 | Deadline |

---

## Success Criteria
- Video under 90 seconds
- Text readable at mobile resolution
- DM narration visible and compelling
- No errors during demo recording
- Tweet posted tagging @NousResearch before May 3
