# D20 Deployment Runbook

**Status:** active  
**Last updated:** 2026-04-24  
**Maintainer:** Alpha / cron agents

This is the canonical deploy runbook for the live D20 stack at `https://agentdungeon.com`.

## Production topology

```text
Public player / portal
        |
        v
Traefik / Coolify HTTPS route: agentdungeon.com
        |
        v
Docker Compose project on VPS: /home/admin/apps/d20
        |
        +-- d20-rules-server  (FastAPI rules/referee, localhost:8600)
        +-- d20-dm-runtime    (FastAPI DM runtime + Hermes agent, localhost:8610)
        +-- d20-redis         (per-character lock/cache support)
```

VPS SSH target for maintainers is environment-specific and intentionally not committed here. Configure your own deployment host or private inventory before running deploy commands.

```bash
ssh <your-user>@<your-vps-host>
```

Do **not** rely on laptop-only SSH aliases from cron/sandbox agents.

## Canonical DM architecture

The DM is a **Hermes agent inside the `d20-dm-runtime` Docker container**.

Hard rules:

1. The live DM profile is inside the VPS container at `/root/.hermes/profiles/d20-dm`.
2. `HERMES_HOME=/root/.hermes` inside `d20-dm-runtime`.
3. The laptop/global profile `~/.hermes/profiles/d20-dm` must not be created or used.
4. `dm-runtime/hermes-home/profiles/d20-dm/` in the repo is a Docker build/source artifact only.
5. Host-side DM proxy containers/ports are obsolete. The old `8611` proxy architecture must stay dead.
6. Rules server owns state/rules/rolls. DM runtime owns narration/choice framing only.
7. Rules-server augmentation must call `/dm/narrate`, not `/dm/turn`, to avoid recursion/lock conflicts.
8. Public player input uses `/dm/turn`.

Correct runtime invocation, from inside the container only:

```bash
docker exec d20-dm-runtime hermes chat -q "compiled context" -Q --profile d20-dm
```

Expected narrator health:

```json
{
  "mode": "hermes",
  "hermes_home": "/root/.hermes",
  "hermes_profile": "d20-dm",
  "runtime_ready": true,
  "binary_ok": true,
  "binary_help_ok": true
}
```

## One-command DM runtime deploy

Use the cron-safe deploy script:

```bash
cd /home/rigario/Projects/rigario-d20
scripts/deploy_dm_runtime.sh
```

The script performs:

1. Local syntax checks for DM runtime modules.
2. Targeted regression tests:
   - `tests/test_dm_agent_flow_contract.py`
   - `tests/test_dm_runtime_synthesis.py`
3. **NEW: Deployment parity check** — three-way validation (local source ↔ VPS host ↔ container).
4. Required `_extract_trace` parity check (legacy ad-hoc, retained for backward compatibility).
5. `rsync` of `dm-runtime/` to `/home/admin/apps/d20/dm-runtime/`.
6. VPS source sanity checks.
7. `docker compose -f docker-compose.yml -f docker-compose.override.yml build d20-dm-runtime --no-cache`.
8. `docker compose ... up -d --no-deps --force-recreate d20-dm-runtime`.
9. Container source/hash checks via full parity validation.
10. Public `/health` and `/dm/health` checks.
11. Real `/dm/turn` validation through `scripts/validate_actual_dm_agent_turn.py`.
12. Recent log grep for `NameError`, `Traceback`, `Internal Server Error`, Hermes failures, or 401s.

Useful environment overrides:

```bash
VERIFY_ONLY=1 scripts/deploy_dm_runtime.sh      # no sync/build/recreate; verify live only
RUN_TESTS=0 scripts/deploy_dm_runtime.sh        # skip local pytest, not recommended
NO_CACHE=0 scripts/deploy_dm_runtime.sh         # allow Docker cache, not recommended for dependency changes
MAX_TURN_SECONDS=120 scripts/deploy_dm_runtime.sh
VPS_HOST=${VPS_HOST:-<your-user>@<your-vps-host>} scripts/deploy_dm_runtime.sh
PUBLIC_BASE=https://agentdungeon.com scripts/deploy_dm_runtime.sh
```

## Manual DM runtime deploy fallback

If the script fails and you must do it manually:

```bash
cd /home/rigario/Projects/rigario-d20
python3 -m py_compile \
  dm-runtime/app/main.py \
  dm-runtime/app/routers/turn.py \
  dm-runtime/app/services/synthesis.py \
  dm-runtime/app/services/dm_profile.py \
  dm-runtime/app/services/intent_router.py

uv run pytest tests/test_dm_agent_flow_contract.py tests/test_dm_runtime_synthesis.py -q --tb=short

rsync -az --delete \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='hermes-home/profiles/*/sessions/' \
  --exclude='hermes-home/profiles/*/lcm.db*' \
  --exclude='hermes-home/profiles/*/*.log' \
  dm-runtime/ ${VPS_HOST:-<your-user>@<your-vps-host>}:/home/admin/apps/d20/dm-runtime/

ssh ${VPS_HOST:-<your-user>@<your-vps-host>} '
set -Eeuo pipefail
cd /home/admin/apps/d20
chmod -R u+rwX,go+rX dm-runtime/hermes-home || true
grep -n "def _extract_trace\|_extract_trace(server_result)" dm-runtime/app/services/synthesis.py
docker compose -f docker-compose.yml -f docker-compose.override.yml build d20-dm-runtime --no-cache
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --no-deps --force-recreate d20-dm-runtime
sleep 8
docker ps --filter name=d20 --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker exec d20-dm-runtime sh -lc "grep -n \"def _extract_trace\|_extract_trace(server_result)\" /app/app/services/synthesis.py && sha256sum /app/app/services/synthesis.py && python3 -m py_compile /app/app/services/synthesis.py"
'

python3 scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 90
```

## Rules server deploy

Use rules-server deploy only when `app/`, root `Dockerfile`, static assets, or rules-server requirements change. Do not rebuild rules-server for DM-runtime-only changes.

Critical rules-server invariants:

- Use both compose files: `docker-compose.yml` and `docker-compose.override.yml`.
- Do not wipe named volumes unless explicitly instructed.
- DB migrations must be additive/idempotent.
- No seed/test data in production unless the task explicitly calls for production seed and the script is idempotent.

## Post-deploy acceptance criteria

A deploy is not done until all of these are true:

```bash
curl -s https://agentdungeon.com/health
curl -s https://agentdungeon.com/dm/health
python3 scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 90
```

Required proof:

- `/health` returns 200.
- `/dm/health` returns 200 with `narrator.mode == "hermes"` and `runtime_ready == true`.
- Fresh `/dm/turn` returns 200.
- Response includes a non-empty `session_id` generated by Hermes.
- `narration.scene` is non-empty.
- `server_trace.server_endpoint_called` is present.
- Recent `d20-dm-runtime` logs show no `NameError`, traceback, `Internal Server Error`, Hermes failure, or 401.
- **NEW: `scripts/check_deployment_parity.py --stage=container` exits 0** — confirms container code matches local source and required symbols are present (prevents silent deployment drift).

## Deployment parity check

**Purpose.** Prevent silent drift between local source, VPS host files, and the running container — the root cause of the 2026-04-24 `/dm/turn 500` outage.

**What it checks.** `scripts/check_deployment_parity.py` validates three-way consistency:

| Stage       | What is verified                                                                 |
|-------------|----------------------------------------------------------------------------------|
| `local`     | Local dm-runtime source files are syntactically valid and contain required symbols. |
| `vps`       | VPS host files (`/home/admin/apps/d20/dm-runtime/app/`) match local hashes and symbols. Runs **after `rsync` but before `docker build`**; non-zero exit aborts the deploy. |
| `container` | Files *inside the running container* (`/app/app/`) match local hashes and symbols. Runs **after `docker compose up`**; non-zero exit signals image/runtime mismatch. |

**Critical files and symbols.** Each file in `FILES_TO_CHECK` must match SHA256 and expose required functions:

- `services/synthesis.py` → `_extract_trace`, `_build_absurd_refusal`, `synthesize_narration`
- `services/intent_router.py` → `_extract_error_status`
- `routers/turn.py`, `main.py` → presence + hash match (no symbol constraints)

**How to run.**

```bash
# full suite (local + VPS + container) — for deploy integration only
python3 scripts/check_deployment_parity.py

# individual stages (used by deploy_dm_runtime.sh)
python3 scripts/check_deployment_parity.py --stage=local     # local-only sanity
python3 scripts/check_deployment_parity.py --stage=vps       # VPS host vs local
python3 scripts/check_deployment_parity.py --stage=container # container vs local
```

**CI/Deploy integration.** The parity check is automatically invoked by `scripts/deploy_dm_runtime.sh`:
- After `rsync` → `--stage=vps` (blocks build if drift detected)
- After container up → `--stage=container` (validates built artifact)
- Failures print detailed mismatch reports and exit non-zero to halt deployment.

**Historical failures this prevents.**
- Missing `_extract_trace` in deployed `synthesis.py` → NameError → `/dm/turn 500`
- Stale `intent_router.py` / `turn.py` on VPS not rebuilt → degraded DM narrator → passthrough fallback / 401 → missing DM prose
- Container built from outdated context → host/container code divergence undetected

## Known failure signatures

### Green health + `/dm/turn` 500

Most likely deployment drift in `dm-runtime/app/services/synthesis.py`.

Check:

```bash
ssh ${VPS_HOST:-<your-user>@<your-vps-host>} 'docker exec d20-dm-runtime grep -n "def _extract_trace\|_extract_trace(server_result)" /app/app/services/synthesis.py || true'
grep -n "def _extract_trace\|_extract_trace(server_result)" dm-runtime/app/services/synthesis.py
```

If the container shows call sites but no definition, sync/rebuild DM runtime.

### Hotpatch appears correct but traceback still references old code

Python already imported the old module. Restart/recreate the service. Hotpatch alone is not proof.

### Docker build fails on `dm-runtime/hermes-home: permission denied`

Fix build-context permissions:

```bash
ssh ${VPS_HOST:-<your-user>@<your-vps-host>} 'cd /home/admin/apps/d20 && sudo chmod -R u+rwX,go+rX dm-runtime/hermes-home'
```

Then rerun the deploy script.

### Hermes smoke succeeds but `/dm/turn` fails

`hermes chat` only proves profile/API readiness. `/dm/turn` also exercises intent routing, rules-server calls, and synthesis. Debug `synthesis.py`, `turn.py`, and rules-client responses before changing provider config.

## Cron-agent guidance

For heartbeat/cron agents:

1. Load `d20-dm-runtime-deploy` and `d20-deployment-audit` skills.
2. If a DM-runtime code change is ready, run `scripts/deploy_dm_runtime.sh` from `/home/rigario/Projects/rigario-d20`.
3. If only checking state, run `VERIFY_ONLY=1 scripts/deploy_dm_runtime.sh`.
4. Update Mission Control only after the script's final validator passes.
5. Include command outputs in heartbeat proof.
