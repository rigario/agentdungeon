#!/usr/bin/env bash
# Deploy only the AgentDungeon DM runtime service, then prove the real /dm/turn path works.
# Designed for automation: non-interactive, fail-fast, and proof-heavy.
set -Eeuo pipefail

LOCAL_ROOT="${LOCAL_ROOT:-$(pwd)}"
DEPLOY_HOST="${DEPLOY_HOST:-<your-user>@<host>}"
DEPLOY_APP_DIR="${DEPLOY_APP_DIR:-/path/to/agentdungeon}"
PUBLIC_BASE="${PUBLIC_BASE:-https://agentdungeon.com}"
MAX_TURN_SECONDS="${MAX_TURN_SECONDS:-90}"
RUN_TESTS="${RUN_TESTS:-1}"
NO_CACHE="${NO_CACHE:-1}"
VERIFY_ONLY="${VERIFY_ONLY:-0}"

log() { printf '\n[%s] %s\n' "$(date -Is)" "$*"; }
run() { log "+ $*"; "$@"; }

if [[ ! -d "$LOCAL_ROOT/dm-runtime/app" ]]; then
  echo "ERROR: LOCAL_ROOT does not look like rigario-d20: $LOCAL_ROOT" >&2
  exit 2
fi

cd "$LOCAL_ROOT"

log "D20 DM runtime deploy starting"
log "LOCAL_ROOT=$LOCAL_ROOT DEPLOY_HOST=$DEPLOY_HOST DEPLOY_APP_DIR=$DEPLOY_APP_DIR PUBLIC_BASE=$PUBLIC_BASE VERIFY_ONLY=$VERIFY_ONLY"

log "Local git state"
git rev-parse --short HEAD || true
git status --short || true

log "Local preflight: syntax checks"
run python3 -m py_compile \
  dm-runtime/app/main.py \
  dm-runtime/app/routers/turn.py \
  dm-runtime/app/services/synthesis.py \
  dm-runtime/app/services/dm_profile.py \
  dm-runtime/app/services/intent_router.py

log "Local preflight: required synthesis helper parity"
grep -n "def _extract_trace\|_extract_trace(server_result)" dm-runtime/app/services/synthesis.py

if [[ "$RUN_TESTS" == "1" ]]; then
  log "Local preflight: targeted regression tests"
  run python3 -m pytest tests/test_dm_agent_flow_contract.py tests/test_dm_runtime_synthesis.py -q --tb=short
else
  log "Skipping local tests because RUN_TESTS=$RUN_TESTS"
fi

if [[ "$VERIFY_ONLY" != "1" ]]; then
  log "Sync dm-runtime source to remote active build context"
  # Keep runtime-generated Hermes/session state out of sync, but preserve the source profile/config tree.
  run rsync -az --delete \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='hermes-home/profiles/*/sessions/' \
    --exclude='hermes-home/profiles/*/lcm.db*' \
    --exclude='hermes-home/profiles/*/*.log' \
    --exclude='hermes-home/profiles/*/errors.log' \
    "$LOCAL_ROOT/dm-runtime/" "$DEPLOY_HOST:$DEPLOY_APP_DIR/dm-runtime/"
  log "Copy parity check script to remote host"
  run rsync -az "$LOCAL_ROOT/scripts/check_deployment_parity.py" "$DEPLOY_HOST:$DEPLOY_APP_DIR/scripts/"

  log "Remote pre-build: deployment parity check (local source ↔ remote host files)"
  # FIXED: run parity check LOCALLY (not via SSH) — script uses DEPLOY_HOST internally
  run python3 scripts/check_deployment_parity.py --stage=remote


  log "Remote pre-build checks"
  ssh "$DEPLOY_HOST" "set -Eeuo pipefail
    cd '$DEPLOY_APP_DIR'
    test -f docker-compose.yml
    test -f docker-compose.override.yml
    test -f dm-runtime/Dockerfile
    chmod -R u+rwX,go+rX dm-runtime/hermes-home || true
    grep -n 'def _extract_trace\|_extract_trace(server_result)' dm-runtime/app/services/synthesis.py
    python3 - <<'PY'
from pathlib import Path
p = Path('dm-runtime/app/services/synthesis.py')
text = p.read_text()
assert 'def _extract_trace' in text, 'missing def _extract_trace in remote source'
assert text.count('_extract_trace(server_result)') >= 2, 'missing _extract_trace call sites'
print('remote_source_ok', len(text.splitlines()))
PY"

  log "Build d20-dm-runtime image"
  if [[ "$NO_CACHE" == "1" ]]; then
    ssh "$DEPLOY_HOST" "cd '$DEPLOY_APP_DIR' && docker compose -f docker-compose.yml -f docker-compose.override.yml build d20-dm-runtime --no-cache"
  else
    ssh "$DEPLOY_HOST" "cd '$DEPLOY_APP_DIR' && docker compose -f docker-compose.yml -f docker-compose.override.yml build d20-dm-runtime"
  fi

  log "Recreate d20-dm-runtime with required dependencies"
  ssh "$DEPLOY_HOST" "set -Eeuo pipefail
    cd '$DEPLOY_APP_DIR'
    docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --no-deps d20-dm-runtime
    sleep 8
    docker ps --filter name=d20 --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    docker exec d20-dm-runtime sh -lc 'which hermes && hermes --help >/tmp/hermes-help.txt && head -5 /tmp/hermes-help.txt'
  "
  # FIXED: run remote parity check LOCALLY (container check requires local Docker)
  run python3 scripts/check_deployment_parity.py --stage=remote
fi

log "Public health checks"
python3 - <<PY
import json, urllib.request
for path in ['/health', '/dm/health']:
    url = '${PUBLIC_BASE}'.rstrip('/') + path
    with urllib.request.urlopen(url, timeout=30) as r:
        body = r.read().decode('utf-8', 'replace')
    print(path, r.status, body[:1200])
    if r.status != 200:
        raise SystemExit(f'{path} returned {r.status}')
    if path == '/dm/health':
        data = json.loads(body)
        narrator = data.get('narrator') or {}
        assert narrator.get('mode') == 'hermes', narrator
        assert narrator.get('runtime_ready') is True, narrator
PY

log "Actual DM-agent /dm/turn validation"
run python3 scripts/validate_actual_dm_agent_turn.py --base "$PUBLIC_BASE" --max-turn-seconds "$MAX_TURN_SECONDS"

log "Recent DM runtime error check"
ssh "$DEPLOY_HOST" "docker logs d20-dm-runtime --since 5m 2>&1 | grep -E 'NameError|Traceback|Internal Server Error|Hermes mode failed|401' || true"

log "D20 DM runtime deploy verified"
