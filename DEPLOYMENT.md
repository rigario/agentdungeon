# AgentDungeon Deployment Runbook

This runbook is intentionally deployment-provider neutral. Replace the placeholder host, path, and public base URL with your own environment.

## Required environment

```bash
export DEPLOY_HOST='<user>@<host>'
export DEPLOY_APP_DIR='/path/to/agentdungeon'
export PUBLIC_BASE='https://your-domain.example'
```

## Topology

```text
Public HTTPS endpoint
    -> reverse proxy / ingress
        -> rules server container
        -> DM runtime container
        -> Redis-compatible lock/cache service
        -> persistent database volume
```

## DM runtime architecture

The DM is a Hermes profile running inside the DM runtime container. Do not commit auth files, local sessions, generated skill bundles, model caches, or host-specific profile state.

Hard rules:

1. Rules server owns state, rules, rolls, fronts, flags, and `world_context`.
2. DM runtime owns narration, NPC voice, pacing, and choice framing.
3. Rules-server augmentation calls `/dm/narrate`; public player input calls `/dm/turn`.
4. Credentials and host inventory live outside git.

## Deploy DM runtime

```bash
DEPLOY_HOST='<user>@<host>' DEPLOY_APP_DIR='/path/to/agentdungeon' PUBLIC_BASE='https://your-domain.example' scripts/deploy_dm_runtime.sh
```

The script performs local syntax checks, targeted regression tests, source sync, container rebuild/recreate, public health checks, and a real `/dm/turn` validation.

Useful overrides:

```bash
VERIFY_ONLY=1 scripts/deploy_dm_runtime.sh
RUN_TESTS=0 scripts/deploy_dm_runtime.sh
NO_CACHE=0 scripts/deploy_dm_runtime.sh
MAX_TURN_SECONDS=120 scripts/deploy_dm_runtime.sh
```

## Rules server deploy

Use a rules-server deploy only when `app/`, root `Dockerfile`, static assets, or rules-server requirements change. DB migrations must be additive and idempotent. Do not wipe volumes or seed test data into a public deployment.

## Post-deploy acceptance criteria

```bash
curl -s "$PUBLIC_BASE/health"
curl -s "$PUBLIC_BASE/dm/health"
python3 scripts/validate_actual_dm_agent_turn.py --base "$PUBLIC_BASE" --max-turn-seconds 90
```

Required proof:

- `/health` returns 200.
- `/dm/health` returns 200 and reports the narrator runtime ready.
- Fresh `/dm/turn` returns 200.
- Response includes bounded narration plus trace/mechanics fields.
- Recent container logs show no traceback, internal server error, auth failure, or narrator failure.
- Deployment parity check passes for local, remote-host, and running-container stages when those checks are available.

## Deployment parity check

`python3 scripts/check_deployment_parity.py` validates that local DM runtime files match the remote host files and/or running container files.

```bash
python3 scripts/check_deployment_parity.py --stage=local
python3 scripts/check_deployment_parity.py --stage=remote
python3 scripts/check_deployment_parity.py --stage=container
```

Use `remote` for remote-host parity checks.
