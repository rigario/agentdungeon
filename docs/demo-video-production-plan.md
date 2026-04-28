# D20 Demo Video Production Plan

**Purpose:** Create a hackathon-ready demo video that does not feel like narration over Discord or terminal text. The video should make D20 feel like a persistent, rules-grounded RPG world where humans and AI agents can choose how involved they want to be.

**Target runtime:** 2:45–3:30

**Primary thesis:**

> D20 is a persistent RPG world for humans and agents, with rules-grounded autonomy you can dial up or down.

**Best short tagline:**

> Natural-language freedom. Server-authoritative consequences. Tunable human involvement.

---

## 1. The Three Pillars the Video Must Prove

### Pillar 1 — Fully Interactive Persistent World

D20 is not a one-off AI chat. It is a persistent RPG world with characters, locations, NPCs, items, maps, lore, campaign state, and consequences that survive across sessions.

**Viewer should understand:**

> “This is a playable world, not just a fantasy chatbot.”

### Pillar 2 — DM Agent Grounded by Rules Server

The Dungeon Master agent can interpret flexible player language, but it does not directly invent or mutate game state. The DM may infer intent, but the server remains the referee.

**Core line:**

> The DM interprets. The server validates. The world persists.

**Important details to communicate simply:**

- Deterministic routing handles clear actions first.
- Flexible/ambiguous actions can go through the DM-agent fallback resolver.
- The fallback maps natural language into canonical actions such as move, interact, explore, rest, attack, cast, quest, puzzle, or look.
- Proposed actions and targets are validated against current scene affordances.
- No invented targets.
- No invented actions.
- No direct database writes from the DM runtime.
- Real mutations go through rules-server endpoints.

### Pillar 3 — Tunable Human Involvement

D20 does not force one style of play. The player chooses how involved they want to be.

**Modes to show/explain:**

1. **Manual play:** player makes every move.
2. **Assisted play:** DM interprets flexible language and keeps flow smooth.
3. **Supervised autonomy:** agents can handle routine exploration or campaign progress under rules-server constraints.
4. **Drop-in resume:** player returns later to persistent campaign state.

**Core line:**

> Play every turn, supervise lightly, or drop back into a world that remembers.

---

## 2. Visual Strategy

The gameplay surface may be text-based through Discord or terminal, but the video should not look like a terminal demo.

### Product framing

- **Portal = world surface / game board**
- **Player section + character sheet = durable character proof**
- **Discord or terminal = input/controller**
- **Overlays = explanation layer**

### Core visual pattern

Use split-screen or quick cuts:

```text
┌──────────────────────────────┬──────────────────────────────┐
│ Player action / DM response  │ Portal player sheet + map     │
│ Discord or terminal          │ Live state proof              │
└──────────────────────────────┴──────────────────────────────┘
```

The viewer should repeatedly see:

```text
Action → DM interpretation → server validation → visible state update
```

### Do not do

- Do not spend long periods scrolling through terminal output.
- Do not make Discord the whole video.
- Do not show raw JSON except as a fast proof flash.
- Do not explain architecture before showing gameplay.

---

## 3. Recommended Video Structure

### 0:00–0:10 — Hook: A World That Remembers

**Show:**

- Fast cuts of portal, character sheet, map, DM response, Thornhold.
- Avoid opening on terminal.

**Narration:**

> Most AI RPGs are disposable conversations. D20 is a persistent world that remembers — and keeps moving at the level of involvement you choose.

**On-screen text:**

```text
A persistent RPG world for humans and AI agents
```

---

### 0:10–0:35 — Player Section + Durable Character Sheet

**Show:**

- Portal Player section.
- Full character sheet.
- Character name, stats, inventory, location, status, quest/campaign state.

**Narration:**

> Every player enters as a durable character, with persistent stats, inventory, location, and campaign state. This is not a temporary chat session — it is a character inside a world.

**On-screen text:**

```text
Durable character identity
Stats • Inventory • Location • Campaign state
```

**Vetting goal:**

The viewer should understand that the new Player section is not just UI polish. It proves persistent character identity.

---

### 0:35–1:10 — Free-Form Natural-Language Gameplay

**Show:**

- Player submits a natural-language action through Discord or terminal.
- Portal remains visible on the other side.

**Best action examples:**

```text
I make my way toward the town square and ask if anyone saw something strange last night.
```

or:

```text
I search the shrine for signs of the Dreaming Hunger.
```

**Narration:**

> Players are not locked into rigid buttons. They can speak naturally, like they would at a real table.

**On-screen text:**

```text
Speak naturally
Free-form player action
```

---

### 1:10–1:45 — DM Interprets, Server Validates

**Show:**

A simple overlay/pipeline, ideally over the real action sequence:

```text
Player action
↓
DM fallback resolver
↓
Scene affordance validation
↓
Rules-server endpoint
↓
Persistent state update
```

Optional proof flash:

- `server_trace` with `_dm_fallback: true`, if readable and not distracting.

**Narration:**

> The DM can interpret intent, but it cannot invent state. If the player uses flexible language, the fallback resolver maps it into a canonical action. Then the rules server validates the action and target against the current scene before anything changes.

**On-screen text:**

```text
DM interprets. Server validates. World persists.
```

**Vetting goal:**

A judge should not leave thinking “the LLM just makes up outcomes.”

---

### 1:45–2:15 — Visible State Change

**Show:**

A before/after state mutation in the portal.

**Preferred proof beat:**

- Before: character sheet says `Location: The Rusty Tankard`.
- Player action: “I make my way toward the town square...”
- After: character sheet/map says `Location: Thornhold Town Square`.

**Alternative proof beats:**

- Inventory gains/loses item.
- NPC met/updated.
- Clue discovered.
- Quest progress updated.
- Combat state changed.

**Narration:**

> Movement, inventory, combat, clues, and quest progress become real campaign state. The chat is not the game. The world state is the game.

**On-screen text:**

```text
Consequences become campaign state
```

---

### 2:15–2:45 — Tunable Human Involvement

**Show:**

Use a control ladder / mode cards overlay over portal footage.

**Recommended overlay:**

```text
Choose your level of involvement

Manual Play          You make every move
Assisted Play        DM keeps flow smooth
Supervised Autonomy  Agents continue routine exploration
Drop-In Resume       Return to persistent campaign state
```

**Narration:**

> The other big idea is control. D20 does not force one style of play. You can play every turn yourself, supervise lightly, let agents handle routine exploration under the same rules-server constraints, or drop back in later to a world that kept its state.

**On-screen text short version:**

```text
Play actively.
Supervise lightly.
Drop back in anytime.
```

**Vetting goal:**

This section should make the agent-native benefit obvious: autonomy is adjustable, not forced.

---

### 2:45–3:15 — Thornhold + Dreaming Hunger

**Show:**

- Thornhold map.
- Lore.
- NPCs.
- Items.
- Player sheet.
- Current quest/story hook.

**Narration:**

> The current playable setting is Thornhold, with lore, maps, NPCs, items, and the mystery of the Dreaming Hunger waiting.

**On-screen text:**

```text
Enter Thornhold
Investigate the Dreaming Hunger
```

**Vetting goal:**

Thornhold gives the system emotional gravity. This should not feel like generic infrastructure.

---

### 3:15–3:30 — CTA

**Show:**

- Best final portal/gameplay shot.
- Character sheet + map or dramatic Thornhold visual.

**Narration:**

> Create a character, enter Thornhold, choose how involved you want to be, and investigate the Dreaming Hunger. Play every turn yourself — or let the campaign keep moving until you return.

**On-screen text:**

```text
D20
The Dungeon Master remembers
```

---

## 4. Full Readable Narration Script

Most AI RPGs are disposable conversations. You ask a model what happens, it invents a scene, and then the world disappears.

D20 is different.

D20 is a persistent RPG world for humans and AI agents — with durable characters, locations, NPCs, items, combat, maps, lore, campaign memory, and a Dungeon Master agent that keeps the world moving across sessions.

Every player enters as a durable character. The player portal gives that identity a home, with a dedicated player section and a full character sheet showing stats, inventory, location, status, and campaign state.

This is not a temporary chat session. It is a character inside a world.

A player or agent can leave, come back later, and continue from the same state — same character, same location, same inventory, same unresolved threats, and the same campaign history.

Players are not locked into rigid buttons. They can speak naturally, like they would at a real table.

They can say: “I make my way toward the town square,” “I ask the guard what happened here,” or “I search the shrine for signs of the Dreaming Hunger.”

But the important part is that the Dungeon Master agent is not simply making up consequences.

D20 uses a layered flow. Clear actions route deterministically. Flexible or ambiguous actions can go through the DM-agent fallback resolver, which maps natural language into canonical actions like move, interact, explore, rest, attack, cast, quest, puzzle, or look.

The DM can interpret what the player probably meant, but the server remains the referee.

The action and target must be validated against the current scene — nearby locations, connected areas, NPCs, interactables, quests, combat enemies, and other server-provided affordances.

No invented targets. No invented actions. No off-world mutations. No direct database writes from the DM runtime.

The DM interprets. The server validates. The world persists.

That is the difference between D20 and a generic AI roleplay chatbot. The model provides judgment, interpretation, and narration, but real consequences go through the rules server and become campaign state.

Movement persists. Inventory persists. Combat state persists. Discovered clues persist. Quest progress persists.

The chat is not the game. The world state is the game.

The other big idea is control.

D20 does not force one style of play. You choose how involved you want to be.

If you want a traditional tabletop session, you can play every turn yourself.

If you want help, the DM can interpret flexible actions and keep the flow moving.

If you want the world to keep advancing, autonomous player agents can continue exploring, asking questions, following leads, or resolving routine moments under the same rules-server constraints.

And when you come back, you are not starting over. You return to the same durable character, same campaign state, and same evolving world.

So D20 can be played actively, supervised lightly, or resumed later. The level of human involvement is tunable.

The current playable setting is Thornhold — a fleshed-out campaign location with lore, maps, items, NPCs, and active story hooks.

Players can enter Thornhold now and investigate the mystery of the Dreaming Hunger.

Instead of every AI game being a disposable one-shot, D20 gives humans and agents a persistent world to inhabit — and gives players a game that remembers.

Natural-language freedom.

Server-authoritative consequences.

Tunable human involvement.

Create a character, enter Thornhold, choose how involved you want to be, and investigate the Dreaming Hunger.

The campaign is already waiting — and the Dungeon Master remembers.

---

## 5. Asset Capture Checklist

Use this as the production shot list. Capture at 1920x1080 if possible. If recording, keep each clip 5–12 seconds unless noted.

### Priority A — Required Assets

These are needed for the video to work.

#### A1. Portal hero / opening shot

- **Type:** screenshot or 5–8s recording
- **Screen:** main portal / best-looking D20 page
- **Must show:** D20 identity, polished UI, Thornhold/world vibe
- **Purpose:** first impression; proves this is not a terminal demo
- **Suggested filename:** `a1-portal-hero.png` or `a1-portal-hero.mp4`

#### A2. New Player section with character sheet

- **Type:** screenshot and optional 5–10s recording scrolling/hovering
- **Screen:** portal Player section
- **Must show:** character name, stats, inventory, current location, status/campaign state if available
- **Purpose:** durable identity proof
- **Suggested filename:** `a2-player-character-sheet.png`

#### A3. Character sheet before action

- **Type:** screenshot
- **Screen:** Player section before action
- **Must show:** current location and/or inventory/quest state
- **Purpose:** before state for action loop
- **Suggested filename:** `a3-character-before.png`

#### A4. Player natural-language action

- **Type:** screenshot or short recording
- **Screen:** Discord or terminal input
- **Preferred text:** `I make my way toward the town square and ask if anyone saw something strange last night.`
- **Purpose:** proves free-form interaction
- **Suggested filename:** `a4-player-freeform-action.png` or `.mp4`

#### A5. DM response to action

- **Type:** screenshot or short recording
- **Screen:** Discord or terminal response
- **Must show:** DM response grounded in world context
- **Purpose:** gameplay proof
- **Suggested filename:** `a5-dm-response.png` or `.mp4`

#### A6. Character sheet / map after action

- **Type:** screenshot
- **Screen:** Player section or map after action
- **Must show:** changed location, clue, NPC, quest, inventory, or other state delta
- **Purpose:** visible persistence proof
- **Suggested filename:** `a6-character-after-state-update.png`

#### A7. Thornhold map

- **Type:** screenshot or 5–8s recording
- **Screen:** map page / Thornhold map
- **Must show:** locations/connections if possible
- **Purpose:** makes the world visual
- **Suggested filename:** `a7-thornhold-map.png`

#### A8. Thornhold lore / NPC / items view

- **Type:** screenshot(s)
- **Screen:** portal world/lore/NPC/items panels
- **Must show:** authored world content beyond chat
- **Purpose:** proves setting depth
- **Suggested filenames:**
  - `a8-lore.png`
  - `a8-npcs.png`
  - `a8-items.png`

#### A9. Dreaming Hunger hook

- **Type:** screenshot
- **Screen:** quest/lore/story hook area
- **Must show:** Dreaming Hunger text or related Thornhold mystery
- **Purpose:** emotional CTA / story anchor
- **Suggested filename:** `a9-dreaming-hunger.png`

#### A10. CTA end card visual

- **Type:** screenshot or generated card
- **Screen:** strongest portal/world shot or title card
- **Must show:** D20 + Thornhold + Dreaming Hunger if possible
- **Purpose:** ending
- **Suggested filename:** `a10-cta-end-card.png`

---

### Priority B — Strongly Recommended Assets

These make the video more persuasive.

#### B1. Split-screen-ready portal + action capture

- **Type:** recording, 10–15s
- **Screen:** capture portal and Discord/terminal side by side if possible
- **Must show:** action and state surface simultaneously
- **Purpose:** avoids talking over terminal text
- **Suggested filename:** `b1-split-action-loop.mp4`

#### B2. Server trace proof flash

- **Type:** screenshot
- **Screen:** response/debug trace
- **Must show:** `_dm_fallback: true` or canonical intent/action if available
- **Purpose:** technical proof for rules-grounded DM
- **Suggested filename:** `b2-server-trace-fallback.png`

#### B3. Rules-server / fallback resolver visual proof

- **Type:** screenshot or generated overlay
- **Screen:** not necessarily raw code; could be a title card
- **Must show:** player action → fallback resolver → validation → state update
- **Purpose:** explains architecture without terminal sludge
- **Suggested filename:** `b3-rules-pipeline-card.png`

#### B4. Invalid/off-world refusal

- **Type:** screenshot or 5s recording
- **Example input:** `I take out my rocket launcher.`
- **Must show:** refusal/no mutation
- **Purpose:** trust signal; no hallucinated gameplay
- **Suggested filename:** `b4-offworld-refusal.png`

#### B5. Ambiguous action clarification

- **Type:** screenshot
- **Example input:** `I go over there.`
- **Must show:** DM asks clarifying question rather than guessing mutation
- **Purpose:** shows safe handling of ambiguity
- **Suggested filename:** `b5-clarify-ambiguous-action.png`

#### B6. No-op narration

- **Type:** screenshot
- **Example:** player asks to move to place they are already at
- **Must show:** safe narration without false state mutation
- **Purpose:** shows integrity boundaries
- **Suggested filename:** `b6-narrate-noop.png`

#### B7. Agent/player identity or auth persistence

- **Type:** screenshot
- **Screen:** agent/player auth, token, resume, session/character association, or repeated login/resume proof
- **Must show:** same durable character across sessions if possible
- **Purpose:** agentic auth / long-term continuity proof
- **Suggested filename:** `b7-agentic-auth-persistence.png`

#### B8. Human-involvement mode card

- **Type:** generated card or screenshot
- **Must show:** Manual Play / Assisted Play / Supervised Autonomy / Drop-In Resume
- **Purpose:** communicates tunable involvement clearly
- **Suggested filename:** `b8-human-involvement-modes.png`

---

### Priority C — Nice-to-Have Assets

These are polish if time allows.

#### C1. Ambient gameplay recording

- **Type:** 20–30s recording
- **Screen:** portal navigation, hover states, map/lore browsing
- **Purpose:** background footage for montage
- **Suggested filename:** `c1-portal-broll.mp4`

#### C2. Combat state proof

- **Type:** screenshot or short recording
- **Must show:** combat state, enemies, hit points, roll, or action result
- **Purpose:** demonstrates mechanical depth
- **Suggested filename:** `c2-combat-state.png`

#### C3. Inventory mutation proof

- **Type:** before/after screenshots
- **Must show:** item gained/lost
- **Purpose:** alternate state mutation if location update is weak
- **Suggested filenames:**
  - `c3-inventory-before.png`
  - `c3-inventory-after.png`

#### C4. NPC interaction proof

- **Type:** screenshot
- **Must show:** player asks NPC something and DM/NPC responds with world context
- **Purpose:** shows broader interaction range
- **Suggested filename:** `c4-npc-interaction.png`

#### C5. Agent acting autonomously

- **Type:** screenshot or short recording
- **Must show:** an agent/player action without manual player input, if available
- **Purpose:** supports supervised autonomy pillar
- **Suggested filename:** `c5-agent-autonomous-action.png`

---

## 6. Asset Capture Order

If time is tight, capture in this exact order:

1. `a2-player-character-sheet.png`
2. `a3-character-before.png`
3. `a4-player-freeform-action.png` or `.mp4`
4. `a5-dm-response.png` or `.mp4`
5. `a6-character-after-state-update.png`
6. `a7-thornhold-map.png`
7. `a9-dreaming-hunger.png`
8. `b8-human-involvement-modes.png` or enough portal B-roll for me to overlay the mode cards
9. `b2-server-trace-fallback.png` if easy
10. `a1-portal-hero.png`

This minimum set is enough to assemble a coherent video.

---

## 7. Recommended Filming / Screenshot Rules

- Use the most polished browser view available.
- Use 1920x1080 if possible.
- Increase browser zoom if text is too small.
- Do not include private keys/tokens/API secrets.
- Avoid showing terminal prompts with sensitive paths unless necessary.
- Keep Discord/terminal shots short and cropped to the player action + DM response.
- Prefer before/after portal screenshots over long scrolls.
- If recording clips, keep the cursor movement slow and deliberate.
- If possible, use the same character throughout the video for continuity.

---

## 8. Editing Plan for Hermes / ffmpeg

Hermes can assemble the final MP4 from screenshots/clips using `ffmpeg`.

### Proposed final assets directory

```text
docs/demo-video-assets/
├── raw/
│   ├── a1-portal-hero.png
│   ├── a2-player-character-sheet.png
│   ├── a3-character-before.png
│   ├── a4-player-freeform-action.png
│   ├── a5-dm-response.png
│   ├── a6-character-after-state-update.png
│   └── ...
├── generated/
│   ├── b3-rules-pipeline-card.png
│   ├── b8-human-involvement-modes.png
│   └── title-cards/
└── final/
    └── d20-demo-video.mp4
```

### Editing style

- 1080p MP4.
- Clean title cards.
- Split-screen action loop.
- Zoom/pan on character sheet and map.
- Short text overlays.
- Optional TTS or recorded voiceover.
- Optional ambient music at low volume.

---

## 9. Must-Hit Final Checklist

The final cut should clearly show or explain:

- [ ] D20 is a persistent RPG world, not a one-off AI chat.
- [ ] Portal has a Player section with a character sheet.
- [ ] Character identity persists across sessions/campaign state.
- [ ] Player can take free-form natural-language actions.
- [ ] DM agent interprets flexible player intent.
- [ ] Rules server validates actions and targets.
- [ ] DM runtime does not invent targets/actions or directly mutate the database.
- [ ] At least one visible state mutation occurs in the portal.
- [ ] Companion portal/map/lore/NPC/items prove the world exists outside chat.
- [ ] Human involvement is tunable: manual, assisted, supervised autonomy, drop-in resume.
- [ ] Agents are framed as optional campaign participants/helpers, not replacements for the player.
- [ ] Thornhold and the Dreaming Hunger provide the CTA.

---

## 10. Red Flags

Revise the video if any of these are true:

- [ ] It looks like a narrated terminal session.
- [ ] It feels like “ChatGPT for D&D.”
- [ ] The portal is not shown early enough.
- [ ] The character sheet is missing or hard to read.
- [ ] There is no before/after state change.
- [ ] The DM appears to free-invent outcomes without server validation.
- [ ] Human involvement tuning is not mentioned.
- [ ] Agent autonomy sounds uncontrolled rather than rules-bounded.
- [ ] Thornhold / Dreaming Hunger feels like an afterthought.

---

## 11. Best One-Scene Demo if We Only Get One Great Clip

**Scene: From the Inn to the Dreaming Hunger**

1. Start on Player section / character sheet.
   - Location: The Rusty Tankard.
   - Quest: Investigate the Dreaming Hunger.
2. Player says:
   - “I make my way toward the town square and ask if anyone saw something strange last night.”
3. DM fallback interprets flexible phrasing.
4. Rules server validates the scene action.
5. DM narrates Thornhold response.
6. Portal updates:
   - Location changes.
   - Clue/NPC/story state appears if available.
7. Overlay:
   - `DM interprets → server validates → world persists`
8. Control ladder appears:
   - `Play actively → supervise lightly → drop back in anytime`
9. CTA:
   - `Enter Thornhold. Investigate the Dreaming Hunger.`

This one scene carries the whole story.

---

## 12. Non-Obvious Dot Connections / Edge Hypotheses

1. **Tunable involvement is the agent-native hook.** Free-form interaction makes D20 playable; rules-server grounding makes it trustworthy; tunable involvement makes it truly agent-native.
2. **The character sheet solves the visual weakness.** Text gameplay becomes credible when each text action visibly changes a durable character/world surface.
3. **Refusal/clarification is a trust signal.** A system that knows when not to mutate state feels more like a real game engine than one that always says yes.
4. **The terminal can be framed as a controller.** Discord/terminal is not the product surface; it is one client into the persistent campaign engine.
5. **The Dreaming Hunger is the emotional anchor.** Without it, the demo risks becoming architecture. The mystery gives viewers a reason to care.

---

## 13. Management / Subtext Read

The risk is not that D20 uses text. Text is normal for tabletop and agent interfaces. The risk is letting the video imply that text is the whole product.

The cut must make this clear:

> Text is how humans and agents speak. The portal is how the world proves it heard them.

The user-control story also needs to be explicit:

> You are not forced to micromanage every turn, and you are not forced to surrender the campaign to agents. You control the throttle.

This is the cleanest way to frame D20 as more than an AI Dungeon clone.

---

## 14. Self-Review & Iteration Loop

This plan integrates the latest product points:

- New portal Player section and character sheet.
- DM-agent fallback resolver for broader natural-language interaction.
- Rules-server authority and integrity boundaries.
- Text-based gameplay reframed through portal/state visuals.
- Tunable human involvement as a headline pillar.
- Thornhold / Dreaming Hunger as the emotional CTA.

If runtime gets tight, cut implementation details first. Do not cut:

1. Character sheet.
2. Free-form action.
3. Server-validated state update.
4. Tunable involvement.
5. Thornhold / Dreaming Hunger CTA.

---

## 15. Proof / Source Notes

This plan is based on:

- D20 project context in this repo.
- User direction that the portal now has a Player section with a character sheet.
- User direction that tunable human involvement is a major demo pillar.
- `docs/dm-agent-fallback-intent-resolver.md`, especially:
  - server remains the referee,
  - fallback resolver maps flexible language to canonical actions,
  - validation against scene affordances,
  - no invented targets/actions,
  - no direct database writes,
  - server-authoritative mutation.
- Demo-first hackathon framing: movie trailer, not feature tour.
- Hermes headless-video assembly workflow using screenshots/clips, overlays, narration, and ffmpeg.
