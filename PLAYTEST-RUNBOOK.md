---
title: D20 Playtest Runbook
project: rigario-d20-agent-rpg
type: runbook
status: active
last_updated: 2026-04-22
maintainer: Alpha
tags: [playtest, agentic, dm-runtime, human-agentic-loop]
---

# D20 Playtest Runbook — "The Dreaming Hunger"

**Project:** Rigario D20 Agent RPG  
**Status:** Pre-Phase 1 (Internal Alpha)  
**Last Updated:** 2026-04-22  
**Maintainer:** Alpha (Hermes Agent)  
**Attached To:** `rigario-d20-agent-rpg` Mission Control project

---

## Executive Summary

### Goal
Validate the **human-agentic play loop**:
- **Human** sets strategy, approves at checkpoints, reviews lore
- **Agent** (DM + Player agent) handles moment-to-moment gameplay
- **Regular summaries** from DM to human
- **Checkpoint gating** at major decisions (quests, combat tactics, moral choices, endings)

### Current State (2026-04-22 — Post-HB209 Verification)

**Execution Path Status** (all green):
- ✅ e754c915 — Hermes DM profile on Kimi Turbo + wrapper service
- ✅ cbd65d2a — End-to-end DM path for playtest
- ✅ d572bb09 — Antechamber puzzle write path (depends on statue flag)
- ✅ f829f9d4 — Internal playtest gate (209 tests pass)

**Infrastructure:**
- ✅ All services deployed: rules-server (:8600), dm-runtime (:8610), redis, Traefik
- ✅ Production live: https://d20.holocronlabs.ai (HTTPS, Let's Encrypt)
- ✅ `/dm/turn` endpoint working with **Kimi Turbo k2.5** narration (~1s latency)
- ✅ Character creation, exploration, direct actions functional
- ✅ All 3 endings reachable (Reseal, Merge, Communion)
- ✅ 209 unit + integration tests passing across dm-runtime and rules-server

**Issues Resolved (since 2026-04-21 playtest):**
- ✅ `thornhold_statue_observed` flag now sets correctly on Thornhold explore — **test_statue_flag.py PASS** (commit eb0a854)
- ✅ `/dm/turn` 404 routing → fixed (Traefik path-based routing)
- ✅ DM timeout (45s+) → fixed (8s timeout, connection pooling, ~347ms avg)
- ✅ Point buy rejects >15 before racial → enforced (returns 400)

**Remaining Blockers:**
- ❌ **Combat choices array always empty** — DM `/dm/turn` responses have `choices: []` during combat (task a9f3b53e, P1-High)
- ❌ **Combat damage not applied** — HP unchanged after enemy attacks (data seeding gap, not code logic)
- ⚠️ **Move action returns 404** — `POST /actions` with `action_type='move'` not recognized; workaround: use `explore` (task 4df7c9f6, P2-Medium)
- ⚠️ **Absurd action routing** — DM misroutes impossible actions (e.g., "swallow statue") to movement instead of narrating refusal (task d8435ba1, P2-Medium)

**Playtest Readiness:** **MINOR BLOCKERS** — core loop works (create → explore → interact → combat → death). Combat needs choices/damage fix for full engagement.

---

## Architecture Overview

### Three-Entity Model

```
Player Agent (your agent)          DM Agent (our VPS)          Rules Server (VPS)
──────────────                     ──────────────              ─────────────────
Creates character ──────────────→  Narrates arrival
Makes decisions                    Voices NPCs
Submits actions                    Presents choices
                                    ↓ calls
                              Validates rules
                              Stores state
                              Returns world_context
```

### Key Endpoints

| Endpoint | Purpose | Auth | Status |
|----------|---------|------|--------|
| `POST /characters` | Create character | None | ✅ 201 |
| `GET /characters/{id}` | Get full state | None | ✅ 200 |
| `POST /characters/{id}/actions` | Direct action (explore/move/rest) | None | ✅ 200 |
| `POST /dm/turn` | DM-mediated play (natural language) | None | ✅ 200 |
| `GET /dm/health` | DM runtime health | None | ✅ 200 |

---

## Playtest Strategy

### Human-Agentic Loop

**Human provides:**
- Character concept & strategy
- Approval at checkpoints
- Lore review & summaries

**Agent provides:**
- Day-to-day gameplay via `/dm/turn`
- Regular session summaries
- Flag/quest tracking
- Progression reports

### Checkpoint Types (Human Gates)

| Gate | Trigger | Human Decision |
|------|---------|----------------|
| Quest Offered | DM presents quest dialogue | Accept/Decline |
| Combat Start | Enemy encounter, choices appear | Tactical approach |
| Moral Choice | Front advancement, NPC dilemma | Which path |
| Major Branch | Kol backstory, Drenna confession | Reveal truth or withhold |
| Ending Available | Seal chamber, Moonpetal Glade | Which path |

### Regular Summary Cadence

- **Per session** (20-30 min): DM sends recap
- **Per location change**: Brief atmosphere note
- **Per flag set**: "New clue discovered"
- **Per quest update**: Status change
- **End-of-day**: Full character state dump

---

## Test Harnesses

### Agentic Test Harness (Primary)

**Script:** `scripts/agentic_harness.py`

**Purpose:** Autonomous stress-test of full game loop.

**Usage:**
```bash
python3 scripts/agentic_harness.py
# Skip combat:
D20_COMBAT=0 python3 scripts/agentic_harness.py
```

**Output:** JSON report with verdict (`READY`, `MINOR_BLOCKERS`, `CRITICAL_BLOCKERS`)

### Human-Gated Playtest Script

**Script:** `scripts/full_playthrough_with_gates.py`

**Purpose:** Run full narrative arc, pausing at 8 human decision points.

### Smoke Test

**Script:** `scripts/smoke_test.py`

**Purpose:** 30-second sanity check before every session.

---

## Phase 0 — Infrastructure & Smoke

**Checklist:**
- [ ] All services healthy (`/health`, `/dm/health`)
- [ ] `/dm/turn` returns 200 with narration
- [ ] Hermes `d20-dm` profile exists on VPS
- [ ] Portal deployed (`/portal.html`)
- [ ] KIMI_API_KEY set (for full DM narration)

**Run smoke test before every session.**

---

## Phase 1 — Agentic Play Loop

**Objective:** Validate autonomous agent can complete full narrative arc.

**Test Character:** Human Fighter / Soldier (STR 15, DEX 14, CON 13, INT 10, WIS 12, CHA 8)

**Core Flow:**
1. Create character
2. Explore Thornhold + examine statue (**check flag**)
3. Talk to Aldric
4. South Road → wolves encounter
5. Combat via DM turn
6. Drenna quest
7. Whisperwood Cave + Kol dialogue (**check flag**)
8. Rest
9. Try all 3 endings

**Success Criteria:**
- All 3 endings reachable
- Statue flag sets
- Combat produces choices
- No 5xx errors
- DM narration latency ≤10s average

---

## Known Issues & Blockers (2026-04-22 — Post-HB209 Verification)

**Last full playtest:** 12/15 steps passed | **Character:** playtest-hero-38cc9e
**See:** `/tmp/d20_playtest_full_20260422_175616.json` | **Test suite:** 209 passing tests

### P1-High (Blocks narrative arc)

| # | Issue | Status | Evidence |
|---|-------|--------|----------|
| 1 | Combat choices array always empty — DM returns `choices: []` during combat | ❌ OPEN (a9f3b53e) | Combat produces no tactical choices; player cannot select attack/spell/flee |
| 2 | Combat damage NOT applied to HP — enemy attacks don't reduce character HP | ❌ OPEN (data seeding) | HP stayed at max after combat; event logged but no mechanical effect |
| 3 | `kol_backstory_known` flag not set after Kol dialogue | ⚠️ VERIFY | Need explicit conversation test; flags dict may be empty |
| 4 | `thornhold_statue_observed` flag NEVER sets | ✅ FIXED (eb0a854) | test_statue_flag.py PASS; flag now inserts correctly on Thornhold explore |

### P2-Medium (Functional gaps)

| # | Issue | Status | Evidence |
|---|-------|--------|----------|
| 5 | POST /actions with `action_type=move` returns 404 | ⚠️ OPEN (4df7c9f6) | "move" not recognized; workaround: use "explore" |
| 6 | DM misroutes absurd actions as movement | ⚠️ OPEN (d8435ba1) | "I swallow the statue" → "Traveled to Whisperwood Edge" |
| 7 | AC and Level returning null in character state | ⚠️ VERIFY | `ac: null, level: null` reported on some characters |
| 8 | Point buy accepts <27 points (total not enforced) | ⚠️ OPEN (f77891b7) | All-10s stats returns 201 (should sum to 27; returns 400) |

### Fixed (since 2026-04-21 playtest)

- ✅ `/dm/turn` 404 routing — Traefik path-based routing deployed (2026-04-22)
- ✅ DM /turn timeout (45s+) — shared httpx pool + 8s timeout, avg 347ms (commit 12506f7d)
- ✅ `thornhold_statue_observed` flag — explore handler now writes narrative_flags (test_statue_flag.py PASS)
- ✅ Point buy rejects stat >15 before racial — returns 400 for invalid stat分配
- ✅ All 4 execution path tasks complete (e754c915 → f829f9d4) — 209 tests pass

---

## Success Criteria

**Phase 1 Complete When:**
- Agentic harness passes with ≤2 minor failures
- All 3 endings reachable with narration
- ✅ Statue flag sets correctly (FIXED 2026-04-20, eb0a854, test_statue_flag.py PASS)
- Combat produces choices (a9f3b53e)
- No critical (P0) bugs

**Phase 3 Ready When:**
- Portal fully wired to DM turn
- Approval gate UI implemented
- 2 external players complete campaign
- Feedback average ≥4/5
- Demo video recorded

---

## Appendix

### Scripts Index

| Script | Purpose | Location |
|--------|---------|----------|
| `agentic_harness.py` | Full autonomous test | `scripts/` |
| `full_playthrough_with_gates.py` | Human-gated test | `scripts/` |
| `smoke_test.py` | Quick health check | `scripts/` |

### Mission Control Project

**Project ID:** `rigario-d20-agent-rpg`  
**URL:** `http://100.98.80.95:8500/project/rigario-d20-agent-rpg`

**Active Tasks:**
- P1: Implement combat choices in DM response (a9f3b53e)
- P1: Verify/restore combat damage application (data seeding fix)
- P1: Verify `kol_backstory_known` flag behavior
- P1: Document blocker status and playtest findings (**THIS DOC** — 0e537b0b)
- P2: Fix POST /actions move returning 404 (4df7c9f6)
- P2: Fix DM absurd action routing (d8435ba1)
- P2: Strengthen point buy total=27 validation (f77891b7)

---

**This document is a living runbook.** Update it after every playtest session. Add new test cases, observations, and findings. All agents should reference this document before starting new D20 work.

**Last verified working state:** 2026-04-22 — `/dm/turn` functional via Traefik with Kimi k2.5 (~1s latency). All 3 endings reachable. Statue flag FIXED. Combat choices remain primary blocker.
