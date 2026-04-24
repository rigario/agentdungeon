# D20 Agent Skills Roadmap

> **For Hermes:** Use this as the tracking source for which agent-facing skills must exist, what each skill teaches, and which code contracts/docs each one depends on.

**Goal:** Make D20 agents reliable by giving each agent a clear skill contract for how to play, narrate, test, deploy, and report issues.

**Architecture:** Skills should mirror the actual runtime contract. The rules server remains authoritative; the DM runtime translates intent and narrates bounded results; the player/playtest agents learn canonical action grammar so they do not accidentally invoke broad turn simulation when they mean local action.

**Status:** Draft tracker created after playtesting exposed ISSUE-016-style local exploration routing gaps.

---

## 1. Tracking Principles

1. **Skills teach real contracts, not vibes.** If a skill tells an agent to use `look`, `stay_put`, or structured action fields, the backend must support and validate those fields.
2. **Natural language stays supported.** Human players can still type freeform requests; skills reduce ambiguity for agents but do not replace router robustness.
3. **Local actions must be explicit.** "Here", "this room", "current location", and "without leaving" must never trigger broad travel simulation.
4. **DM prose and mechanics are separate.** The DM agent narrates; the rules server decides state, rolls, flags, combat, quests, loot, and relationships.
5. **Every skill needs verification hooks.** Each skill should list the endpoint traces and assertions that prove the agent used the right path.

---

## 2. Agent Skill Inventory

| Skill | Audience | Status | Priority | Purpose |
|---|---|---:|---:|---|
| `d20-player-action-grammar` | Player agents, playtest agents | **Needed** | P0 | Teach canonical structured actions: `look`, local `explore`, `interact`, `move`, `rest`, `combat`, `puzzle`, `quest`. |
| `d20-local-exploration-contract` | Implementers, DM runtime agents, verifier agents | **Needed** | P0 | Define backend contract for `look` and `explore` with `scope=current_location` and `stay_put=true`. |
| `d20-playtest-agent-execution` | Playtest agents | **Partially covered** by `d20-playtest-harness`, `d20-playtest-execution`, `d20-playtest-docs` | P0 | How to run DM-agent-first playtests, save full prose, and assert route correctness. Needs explicit local-action assertions. |
| `d20-dm-runtime-intent-routing` | Implementers | **Exists** | P0 | Extend DM intent routing. Needs update after `look`/local action contract lands. |
| `d20-dm-runtime-testing` | Verifiers | **Exists** | P0 | Runtime test workflow. Needs new cases for local look/explore/stay-put behavior and false combat choices. |
| `d20-playtest-issue-triage` | Heartbeat agents | **Partially covered** by `d20-playtest-docs` | P1 | File/update issues from playtest output without corrupting `PLAYTEST-ISSUES.md`; link skills/tasks. |
| `d20-npc-relationship-play` | Player agents, DM/rules implementers | **Needed** | P1 | Teach agents how to chat with useful NPCs over repeated interactions to earn hints/items/discounts once backend supports relationship state. |
| `d20-item-discovery-play` | Player agents, playtest agents | **Needed** | P1 | Exploration should discover useful level-appropriate items, not key lore items. Teaches expected behavior and assertions. |
| `d20-deployment-runtime-parity` | Implementers/verifiers | **Mostly covered** by deploy/audit skills | P1 | Make sure repo -> VPS source -> container -> live endpoints match, especially for DM runtime. |
| `d20-story-boundary-and-anti-cheat` | DM/player/playtest agents | **Partially covered** by guardrail tests | P2 | Prevent claims like being in another location, inventing items, skipping gates, or targeting the DM. |

---

## 3. P0 Skill Specs To Create/Update

### 3.1 `d20-player-action-grammar` — New Skill

**Audience:** Player agents and playtest agents.

**Trigger:** Any agent is deciding what action to take during D20 play.

**Core lesson:** Convert intent into the smallest canonical action. Prefer local `look`/`explore` when the player says they are staying in the current location.

**Canonical grammar:**

```json
{
  "LOOK_CURRENT_LOCATION": {
    "action_type": "look",
    "target": null,
    "details": {"scope": "current_location", "stay_put": true}
  },
  "EXPLORE_CURRENT_LOCATION": {
    "action_type": "explore",
    "target": null,
    "details": {"scope": "current_location", "mode": "search", "stay_put": true}
  },
  "INTERACT_OBJECT": {
    "action_type": "interact",
    "target": "<object_or_npc_name>",
    "details": {"scope": "current_location"}
  },
  "MOVE_LOCATION": {
    "action_type": "move",
    "target": "<location_id>",
    "details": null
  }
}
```

**Decision table:**

| Player phrase | Use | Do not use |
|---|---|---|
| "What do I see?" | `look` | `turn/start` |
| "Look around this room" | `look` | `move`, random `interact` |
| "Search for clues" | local `explore` | broad `continue` |
| "Investigate the statue" | `interact` target `statue` | random NPC fallback |
| "Talk to Marta" | `interact` target `Marta` | `look` |
| "Continue adventuring" | `turn/start` | local `look` |
| "Go to forest-edge" | `move` | `explore` |

**Verification assertions:**

- `server_trace.server_endpoint_called == "actions"` for `look`, local `explore`, `interact`, `move`, `rest`, `quest`, `puzzle`.
- `server_trace.server_endpoint_called == "turn/start"` only for broad adventure simulation.
- For `stay_put=true`, fresh `GET /characters/{id}` shows unchanged `location_id` and `current_location_id`.
- Non-combat local actions must not return combat-only choices unless active combat is present.

---

### 3.2 `d20-local-exploration-contract` — New Skill

**Audience:** Implementers and verifiers.

**Trigger:** Work involving local look/search/examine/stay-here behavior.

**Backend contract to implement:**

1. Add `look` as a rules-server action.
2. Add `LOOK` as a DM runtime intent.
3. Keep `explore` for active searching/loot/clue discovery.
4. Add `details.scope = "current_location"` and `details.stay_put = true` semantics.
5. Prevent generic area targets from random-NPC fallback.
6. Fix false combat-choice detection for non-combat action responses.

**Expected rules-server response for `look`:**

```json
{
  "success": true,
  "narration": "You take in the current location...",
  "events": [{"type": "look", "location_id": "..."}],
  "character_state": {"hp": {"current": 12, "max": 12}, "location_id": "..."},
  "world_context": {
    "location": {},
    "npcs": [],
    "connections": [],
    "interactables": [],
    "active_quests": [],
    "key_items": [],
    "atmosphere": {}
  },
  "available_actions": ["look", "explore", "interact", "move", "rest"]
}
```

**Regression tests required:**

- `test_look_action_returns_current_location_context`
- `test_look_does_not_move_character`
- `test_local_explore_does_not_route_to_turn_start`
- `test_examine_area_does_not_pick_random_npc`
- `test_non_combat_actions_do_not_emit_combat_choices`

---

### 3.3 Update `d20-dm-runtime-intent-routing`

**Add after backend contract exists:**

- `IntentType.LOOK`
- keyword patterns for `look around`, `look closer`, `what do I see`, `examine the area`, `current location`, `this room`, `here`, `without leaving`, `stay here`
- local-presence guard before `_BROAD_PATTERNS`
- payload shaping for `details.scope=current_location`, `details.stay_put=true`
- tests that assert local stay-put language routes to `ACTIONS`, not `TURN`

---

### 3.4 Update `d20-playtest-harness` / `d20-playtest-execution`

**Add required playtest assertions:**

- Every local-action playtest logs `server_trace.intent_used`.
- Every local-action playtest checks the character did not move unless move was intended.
- `dm-prose.md` must cite the exact turn where local look/explore was used.
- If a local action produces combat choices while no active combat exists, file a separate combat-choice issue.

---

## 4. P1 Skill Specs To Create Later

### 4.1 `d20-npc-relationship-play`

**Purpose:** Teach player agents to build relationships with useful NPCs through repeated conversation when backend support lands.

**Design direction:**

- Relationship increases should be server-validated, not DM-invented.
- DM can propose relationship deltas, but rules server confirms.
- Useful outcomes: hints, item access, discounts, trust-gated dialogue.
- Avoid side-quest sprawl; use repeated interactions and compact triggers.

**Candidate structured action:**

```json
{
  "action_type": "interact",
  "target": "Marta",
  "details": {"mode": "conversation", "relationship_intent": "befriend"}
}
```

### 4.2 `d20-item-discovery-play`

**Purpose:** Teach exploration agents and implementers that exploration should find useful level-appropriate items, not lore-critical key items.

**Rules:**

- Key/lore items stay gated by quests, puzzles, or explicit story flags.
- Exploration can reveal consumables, mundane gear, clues, gold, tracks, or local advantages.
- Item drops should be bounded by location and level.

---

## 5. Tracking Workflow

1. **When a gameplay/design issue reveals a missing agent habit:** add a row to this roadmap.
2. **When backend support lands:** create/update the corresponding Hermes skill.
3. **When a skill is created:** mark status `Created` and link to skill name/path.
4. **When a playtest proves the skill works:** mark status `Validated` with evidence path, usually `playtest-runs/.../dm-prose.md`.
5. **When a skill becomes wrong or stale:** patch it immediately; do not wait for a new session.

---

## 6. Recommended Execution Order

1. Implement backend `look`/local exploration contract.
2. Create `d20-player-action-grammar` skill.
3. Create `d20-local-exploration-contract` skill.
4. Patch `d20-dm-runtime-intent-routing` with the new `LOOK` contract.
5. Patch playtest skills with local-action route assertions.
6. Run live playtest: `look`, `explore current location`, `interact statue`, `talk to NPC`, `move`.
7. File/close `PLAYTEST-ISSUES.md` entries with proof.

---

## 7. Open Questions / Edge Hypotheses

1. **Optional structured field on `/dm/turn`:** The cleanest long-term interface may be `message` plus optional `structured_action`; natural language remains fallback.
2. **Agent-to-agent play contract:** Player agent could choose a structured action from `choices`, while human-facing prose stays natural.
3. **DM-proposed relationship deltas:** NPC friendship may require a two-phase commit: DM proposes, rules server validates/applies.
4. **Scene refresh loop:** `look` may become the canonical first action after every move to refresh bounded context.
5. **Combat-choice bug linkage:** False combat choices on local actions may be a synthesis invariant bug independent of local exploration; track separately.

---

## 8. Verification Checklist For This Roadmap

- [ ] File exists at `docs/plans/2026-04-24-d20-agent-skills-roadmap.md`.
- [ ] P0 skills identify exact audience, purpose, contract, and verification.
- [ ] Local exploration issue maps to both backend contract and player-agent skill.
- [ ] Existing skills to update are named explicitly.
- [ ] Execution order starts with backend contract before teaching agents conventions.
