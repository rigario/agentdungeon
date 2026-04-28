# Hackathon Freeze Loose Ends — 2026-04-28

Status: **ready for demo rehearsal / recording path**

Canonical live URL: https://agentdungeon.com

## What was added

### Public agent skills

Committed under `.hermes/skills/`:

- `.hermes/skills/agentdungeon-player/SKILL.md`
- `.hermes/skills/agentdungeon-dm-playstyle/SKILL.md`
- `.hermes/skills/agentdungeon-troubleshooting/SKILL.md`

These teach a public agent how to health-check the live game, create/resume a character, use `/dm/turn`, generate a portal, choose grounded actions, and ask the human only for high-stakes choices.

### Public docs

Added:

- `docs/index.md`
- `docs/agent-play-quickstart.md`
- `docs/api-quickstart.md`
- `docs/dm-runtime-framework.md`
- `docs/architecture/agentdungeon-architecture.md`
- `docs/assets/agentdungeon-architecture.svg`

Updated:

- `README.md` with live demo, docs, public skills, judge path, and DM/framework links.
- `SUBMISSION.md` with live demo/repo/docs pointers.
- `.env.example` to remove placeholder secret values and document safe public configuration.
- `DEPLOYMENT.md`, `docker-compose.override.yml`, and the in-repo board verification skill to remove committed internal host/IP references from public-facing docs.

## Verification run

Timestamp: `2026-04-28 15:20:47 UTC`

### Content validation

```text
OK .hermes/skills/agentdungeon-player/SKILL.md
OK .hermes/skills/agentdungeon-dm-playstyle/SKILL.md
OK .hermes/skills/agentdungeon-troubleshooting/SKILL.md
OK docs/index.md
OK docs/agent-play-quickstart.md
OK docs/api-quickstart.md
OK docs/dm-runtime-framework.md
OK docs/architecture/agentdungeon-architecture.md
OK docs/assets/agentdungeon-architecture.svg
SKILL_OK .hermes/skills/agentdungeon-player/SKILL.md agentdungeon-player
SKILL_OK .hermes/skills/agentdungeon-troubleshooting/SKILL.md agentdungeon-troubleshooting
SKILL_OK .hermes/skills/agentdungeon-dm-playstyle/SKILL.md agentdungeon-dm-playstyle
SVG_OK docs/assets/agentdungeon-architecture.svg
```

### Public docs/link audit

```text
active_docs_old_domain_count 0
missing_links 0

d20.holocronlabs.ai 0 []
vps-8432193b 0 []
15.235.197.208 0 []
100.98.80.95 0 []
ssh admin@ 0 []
```

### Secret-like pattern audit on public docs/skills

```text
.env ignored by .gitignore
findings 0
```

### Production smoke suite

Command:

```bash
SMOKE_RULES_URL=https://agentdungeon.com SMOKE_DM_URL=https://agentdungeon.com python3 -m pytest tests/test_smoke.py -q --tb=short
```

Result:

```text
20 passed in 45.24s
```

### Targeted DM/runtime tests

Command:

```bash
python3 -m pytest \
  dm-runtime/tests/test_intent_fallback.py \
  dm-runtime/tests/test_intent_router_fallback.py \
  dm-runtime/tests/test_narrator_context.py \
  dm-runtime/tests/test_target_normalization.py \
  tests/test_dm_runtime_synthesis.py \
  tests/test_narrator_scope.py \
  -q --tb=short
```

Result:

```text
61 passed in 0.40s
```

### Live judge-path probe

```json
{
  "/health": {"status": 200},
  "/dm/health": {"status": 200},
  "/api/map/data": {"status": 200, "total": 10},
  "create_character": {
    "status": 201,
    "character_id": "judgepath-41d58a-858320",
    "name": "JudgePath-41d58a"
  },
  "dm_turn": {
    "status": 200,
    "has_narration": true,
    "has_choices": true,
    "has_trace": true,
    "session_id": "20260428_152407_ef5820"
  },
  "portal_token": {
    "status": 201,
    "has_token": true
  },
  "portal_state": {
    "status": 200,
    "has_character": true
  }
}
```

## Git commit / push proof

```text
Local commit: 55938b86184d445968b8c2a40a90c6e215639f2c
Commit message: Prepare AgentDungeon hackathon freeze submission
Remote branch: origin/main -> 55938b86184d445968b8c2a40a90c6e215639f2c
Working tree after push: clean
```

## Remaining caveats

- Historical reports/playtest logs may still mention old domains as evidence. Active public docs and skills no longer do.
- Some previously tracked backup files remain in git history/index. I did not remove tracked files without explicit deletion approval. `.gitignore` now prevents new local temp/backups/playtest-run dumps from polluting status.
- Freeze changes were committed and pushed to `origin/main`; the repository now reflects the demo-ready docs/runtime/skills state.
