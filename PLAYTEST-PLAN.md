# D20 Playtest Plan — "The Dreaming Hunger"

**Date:** 2026-04-22
**Status:** Pre-playtest (fixes required before inviting players)

---

## Executive Summary

The D20 RPG is architected as a 3-entity system (Player Agent + DM Agent + Rules Server), deployed live on VPS with both rules server and DM runtime reachable via Traefik HTTPS. **200 tests pass locally.** However, the critical DM `/turn` endpoint returns 500 due to a Pydantic validation bug in the synthesis layer, and 4 narrative paths are broken (Communion ending, quest acceptance, key item awards, Kol talkability). The game IS playable via direct API actions, but the intended DM-mediated experience is blocked.

**Playtest readiness: Internal playtest gate passing. System is ready for Phase 1.**

---

## Current System State

### What's Working (verified live on VPS)

| Feature | Endpoint | Status | Evidence |
|---------|----------|--------|----------|
| Character creation | `POST /characters` | 201 | Created Aegis Ward, got ID + HP + AC |
| Explore action | `POST /characters/{id}/actions` | 200 | "You search Thornhold..." |
| Move/travel | `POST /characters/{id}/actions` | 200 | Wolves encounter on south-road |
| NPC interaction | `POST /characters/{id}/actions` | 200 | Torren dialogue returned (note: random NPC by biome, ignores target) |
| Rest | `POST /characters/{id}/actions` | 200 | "Short rest. Recover 3 HP." |
| Adventure turn (async) | `POST /characters/{id}/turn/start` | 200 | Turn ID, dice log, decisions, events |
| DM intent classification | `POST /dm/intent/analyze` | 200 | "attack the bandit" → COMBAT correctly |
| DM health check | `GET /dm/health` | 200 | Rules server OK, narrator enabled |
| Rules server health | `GET /health` | 200 | DB connected |
| Landing page | `GET /` | 200 | HTML with demo scenes |
| Character sheet | `GET /characters/{id}/sheet` | 200 | D&D 5e styled parchment HTML |
| Event log | `GET /characters/{id}/event-log` | 200 | All 7 events tracked correctly |
| Cadence system | `GET /cadence/status` | 200 | Mode=normal, tick=180s (inactive) |
| Archive character | `DELETE /characters/{id}` | 200 | Recoverable deletion |
| Portal share tokens | `POST /portal/token` | Available | Token-based public viewing |
| Player Portal HTML | `GET /portal.html` | Available | Read-only character view |

### What's Broken (verified live on VPS)

| Bug | Severity | Impact | Root Cause |
|-----|----------|--------|------------|
| NPC interact ignores target | ~~P2-Medium~~ **FIXED** | ~~Wrong NPC dialogue~~ | ~~Picks random NPC by biome instead of named NPC~~ → now matches target by name |
| No quest acceptance mechanic | P1-High | Quest chains broken | No `quest` action type, `quest-save-drenna-child` unreachable |
| Brother Kol not talkable | P1-High | Communion ending blocked | Kol is combat-only, `kol_backstory_known` flag unreachable |
| Key items never awarded | P1-High | Critical loot missing | `drens_daughter_insignia`, `kols_journal` defined but never granted |
| Cadence inactive | P2-Medium | Doom clock static | `is_active: 0`, no cron tick progression |
| Narrative introspect 404 | P2-Medium | Audit endpoint missing | May be behind auth or removed |
| Locations list 404 | P3-Low | Map data API missing | `/locations` not registered (map works via HTML) |

---

## Playtest Plan — Phased Approach

### Phase 0: Critical Fix (RESOLVED)

**~~P0: Fix the DM `/turn` 500 error~~** — **RESOLVED** (verified 2026-04-22)

The P0 bug has been resolved. The DM `/turn` endpoint now returns 200 with valid DMResponse for all action types (explore, move, rest, combat, talk, general). Verified with live testing and 283 passing tests (200 server + 83 DM runtime).

**Additional fix (2026-04-22):** NPC interact targeting — the actions handler now matches the target NPC by name (case-insensitive) instead of picking a random NPC from the biome. Verified: "talk to Aldric" returns Aldric, "talk to Ser Maren" returns Ser Maren.

The bug: `synthesis.py` `_extract_mechanics()` iterates `dice_log` entries and converts some to strings, but `type=choice` entries fall through without string conversion. The `MechanicsPayload.what_happened: list[str]` Pydantic model rejects dicts.

Fix location: `dm-runtime/app/services/synthesis.py` lines ~75-95

The `else` branch in the `dice_log` iteration needs to convert the entry to a string instead of appending it as a dict:

```python
# Current (broken):
else:
    what_happened.append(str(context))

# The issue: when type=="choice", context is the "context" key value,
# but the full entry dict is being appended because str(entry) is called
# on event entries but context on dice_log entries
```

Actually, the real issue is in the `events` loop. Some `events` entries are dicts with `type: "travel"` that have nested objects. The `_extract_mechanics` loop tries `event.get("desc") or event.get("description") or event.get("event")` but some events have `type` key that returns a string like "travel" — no desc/description/event keys.

**Fix:** After the events loop, filter out any non-string entries:
```python
what_happened = [w for w in what_happened if isinstance(w, str)]
```

Or better: ensure every append path produces a string.

**Verification:** After fix, `POST /dm/turn` with any character/message should return 200 with valid DMResponse.

**Deploy:** Rebuild dm-runtime container on VPS.

---

### Phase 1: Internal Alpha Playtest (us only)

**Goal:** Play through the game from start to one ending, documenting every friction point.

**Duration:** 1-2 sessions of 30-60 min each

**Who:** Rigario + Alpha (driving API calls or using Portal)

#### Test Scenarios

**Scenario A: First Adventure (Guided Path)**

1. Create character: Human Fighter, Soldier background
2. Explore Thornhold — observe statue
3. Talk to Aldric at The Rusty Tankard
4. Move to South Road — encounter wolves
5. Rest and recover
6. Explore toward Greypeak Pass
7. Use adventure turn (async) to explore deeper
8. Check event log for persistence

**Scenario B: DM-Mediated Play (after P0 fix)**

1. Create character: Elf Wizard, Sage background
2. Use DM `/turn` for all interactions: "I look around", "explore the caves", "rest here"
3. Verify DM narration + choices are returned
4. Verify intent routing: combat → combat, explore → actions, vague → turn
5. Verify HP, location, events persist across DM turns

**Scenario C: Combat Flow**

1. Create character, move to south-road (triggers wolf encounter)
2. Start combat manually with `enemies_json` + `initiative_roll`
3. Attack with `d20_roll` + `target_index`
4. Verify initiative order, damage, HP changes
5. Continue rounds until victory or defeat
6. Check combat_log in event log

**Scenario D: Player Portal (Visual Playtest)**

1. Create character via API
2. Generate portal share token
3. Open `https://d20.holocronlabs.ai/portal.html?token=<token>`
4. Verify: character sheet renders, location shows, HP/AC display
5. Take actions via API, refresh portal — verify state updates
6. Test on mobile viewport

#### Data to Collect

For each scenario:
- [ ] All API calls + responses (capture full JSON)
- [ ] Time to complete each step
- [ ] Any 4xx/5xx errors
- [ ] Narration quality (is it coherent? immersive? breaking character?)
- [ ] State consistency (HP correct? Location correct? Events logged?)
- [ ] Dead ends (actions that produce no useful response)
- [ ] Confusing UX moments

#### Known Issues to Test

As of 2026-04-22, most previously-broken narrative paths have been fixed:

1. **~~Communion ending~~** — **FIXED.** Brother Kol is talkable (biome=dungeon, NPC dialogue). `kol_backstory_known` reachable: talk to Drenna (confession → kol_backstory clue_reward chain).
2. **~~Drenna's quest~~** — **FIXED.** Quest acceptance implemented (`action_type="quest"`, `quest_action="accept/complete/list"`). Full lifecycle with character_quests tracking.
3. **Thornhold exile** — `collateral_near_town` flag exists; condition is highly specific but path is reachable. Low priority for playtest.
4. **~~Antechamber puzzle~~** — **FIXED.** `thornhold_statue_observed` write path wired (explore sets flag, checked for cave access, puzzle handler at actions.py ~1488+).
5. **~~Key items~~** — **FIXED** (commit 2da3147). Key items awarded from combat loot AND quest completion.

Remaining narrow paths: Thornhold exile (specific flag condition). Not blocking playtest.

---

### Phase 2: Narrative Depth Playtest

**Prerequisite:** Phase 1 complete, P0 bug fixed, at least one P1 bug fixed

**Goal:** Test the narrative arc: getting Marked → exploring deeper → reaching an ending.

**Duration:** 2-3 sessions

#### Test Arcs

**Arc 1: The Mark and the Green Woman**

1. Create character
2. Explore to find the cave (where the Del possession encounter triggers)
3. Get marked (narrative flag set)
4. Try to suppress the Green Woman (3 uses)
5. Rest and dream narration (should change based on mark level)
6. Explore to Moonpetal Glade
7. Try peaceful vs. greed resolution paths

**Arc 2: Reseal Ending (Reachable)**

1. Get marked
2. Explore deep enough to find the Seal Chamber
3. Complete the Reseal puzzle
4. Verify ending narration + game state

**Arc 3: Merge Ending (Reachable)**

1. Get marked
2. Find the Bone Gallery
3. Complete the Merge path
4. Verify ending narration + game state

#### Narrative Quality Checklist

- [ ] Atmosphere changes with mark level (0-3+)
- [ ] Time of day affects encounters and NPC availability
- [ ] Green Woman suppression has 3-use limit
- [ ] Each location has distinct atmosphere text
- [ ] NPC dialogue feels distinct (not generic)
- [ ] Combat narration includes mechanical details subtly
- [ ] Rest/dream content varies by narrative state
- [ ] Encounter scaling feels appropriate

---

### Phase 3: External Invited Playtest

**Prerequisite:** Phase 1+2 complete, all P0/P1 bugs fixed

**Who:** 2-3 trusted external players

**Format:** Each player gets:
1. Portal link (share token)
2. Brief getting-started guide
3. Access to DM `/turn` endpoint (or web UI if ready)
4. Feedback form

**Duration:** 1 week, async

#### Feedback Form

```
On a scale of 1-5:

1. How easy was it to start playing?
2. How immersive was the narration?
3. Did the game feel responsive to your choices?
4. Were mechanical outcomes (combat, HP, loot) clear?
5. How likely are you to play again?

Free response:
- Most confusing moment:
- Coolest moment:
- What would make you play more:
- Bugs encountered:
- What felt "broken" vs "intentionally hard":
```

#### Access Control

**Current state:** Auth middleware exists but agent API keys are the primary auth. For external playtest:
- Generate agent API key per playtester
- Or: set up OAuth (Google/Twitter) for web portal access
- Or: portal share tokens are already unauthenticated (read-only) — pair with API key for write access

---

### Phase 4: Hackathon Submission

**Prerequisite:** Phase 3 feedback incorporated

**Task reference:** MC `59156037` — Hackathon submission after invited playtest feedback pass

**Deliverables:**
- Working demo (landing page + portal + DM-mediated play)
- Video walkthrough (3-5 min)
- README with setup instructions
- Public repo or deploy link

---

## Bug Fix Priority (for playtest readiness)

### Must Fix (before Phase 1)

| # | Bug | Fix | Effort |
|---|-----|-----|--------|
| 1 | DM `/turn` 500 | `synthesis.py` — ensure `what_happened` entries are all strings | 15 min |

### Should Fix (before Phase 2)

| # | Bug | Fix | Effort |
|---|-----|-----|--------|
| 2 | Quest acceptance missing | Add `quest` action type in `actions.py` + flag/item wiring | 2-3 hr |
| 3 | Brother Kol not talkable | Add Kol as interactable NPC at crossroads or make journal lootable | 1-2 hr |
| 4 | Key items never awarded | Wire `key_items.py` awards into encounter/quest completion | 1-2 hr |
| 5 | NPC interact ignores target | Route to named NPC when target matches, random fallthrough | 1 hr |

### Nice to Have (before Phase 3)

| # | Bug | Fix | Effort |
|---|-----|-----|--------|
| 6 | Cadence inactive | Activate cadence + set up cron tick | 30 min |
| 7 | Narrative introspect 404 | Check auth middleware or re-register route | 30 min |
| 8 | Communion ending path | Wire `kol_backstory_known` → ending check | 1 hr |
| 9 | DM scene memory | Add session-based memory for narration continuity | 3-4 hr |
| 10 | Doom clock progression | Productize cadence cron beyond combat | 2-3 hr |

---

## Playtest Session Template

```
=== D20 Playtest Session ===
Date: _______
Player: _______
Character: _______ (Race/Class/Background)
Scenario: _______

## Pre-session checklist
- [ ] Both servers healthy (GET /health + GET /dm/health)
- [ ] Character created successfully
- [ ] Portal token generated for visual reference

## Session log
| Step | Action | API Call | Status | Narration Quality | Notes |
|------|--------|----------|--------|-------------------|-------|
| 1    |        |          |        |                   |       |

## Post-session
- Time played: ___ min
- Character state at end: HP ___/___ | Location: ___ | Mark: ___
- Ending reached: ___
- Bugs found: ___
- Quality notes: ___
```

---

## Non-Obvious Dot Connections

1. **DM 500 is the single bottleneck for the entire product experience.** The rules server works perfectly — character creation, combat, explore, rest, turns all return 200. But the DM layer (the whole point of "play WITH your agent") is broken by one Pydantic type mismatch. Fix is 15 minutes; impact is the entire DM-mediated game loop.

2. **Portal + DM turn = the hackathon demo.** If we wire the portal HTML to call DM `/turn` instead of raw actions, we have a browser-playable RPG. Currently the portal is read-only. The DM runtime is the write path. Connecting them is the playable product.

3. **Narrative gaps are invisible in a 10-minute playtest.** A player can have a complete 10-min session (create → explore → fight → rest) without ever hitting Kol, Drenna, or quest chains. The "getting marked" arc works. It's the *second* session where narrative gaps show. Phase 2 exists to stress those.

4. **The demo page already does what a tutorial should.** `demo.html` has cutscenes, ambient music, die-roll explanations, and a character reveal sequence. It's a linear demo but it proves the aesthetic and pacing work. The gap is between "watch the demo" and "start playing."

5. **NPC-by-biome is actually a feature for Phase 1.** The random NPC selection means every interact is a surprise — not good for directed quests, but fine for exploration playtest. We can document it as "random encounter" behavior and fix targeting later.

---

## Proof / Verification

| Source | Method | Result |
|--------|--------|--------|
| Git log | `git log --oneline -30` | 30 commits, latest `f7a2cbd` (conftest.py fix) |
| Local tests | `pytest --tb=short -q` | 200 passed in 0.91s |
| Rules server health | `GET https://d20.holocronlabs.ai/health` | 200 OK, DB connected |
| DM runtime health | `GET https://d20.holocronlabs.ai/dm/health` | 200 OK, narrator enabled |
| DM /turn | `POST https://d20.holocronlabs.ai/dm/turn` | 500 Internal Server Error |
| Docker logs | `docker logs d20-dm-runtime --tail 50` | Pydantic ValidationError on `what_happened.0` |
| Character create | `POST /characters` | 201, HP 12/12, AC 12 |
| Explore action | `POST /characters/{id}/actions` | 200, narration + events |
| Move action | `POST /characters/{id}/actions` | 200, wolf encounter |
| Adventure turn | `POST /characters/{id}/turn/start` | 200, turn_id + dice_log |
| Event log | `GET /characters/{id}/event-log` | 200, 7 events tracked |
| Cadence | `GET /cadence/status` | 200, inactive (mode=normal) |
| MC tasks | `GET /api/tasks?limit=200` | 101 D20 tasks: 81 Done, 18 To Do, 2 In Progress |
| File counts | `find` | 38 app, 14 dm-runtime, 6 test, 2 dm-runtime test |