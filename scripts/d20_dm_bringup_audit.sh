#!/usr/bin/env bash
# Bring up and audit the D20 DM runtime end-to-end.
#
# This is the canonical "is the DM agent actually working?" gate. It verifies
# more than container health: core files compile, deployed core files match,
# Hermes can produce JSON prose, /dm/health is green, and a fresh /dm/turn
# returns non-empty prose with a non-null Hermes session_id.

set -Eeuo pipefail

LOCAL_ROOT="${LOCAL_ROOT:-$HOME/Projects/rigario-d20}"
VPS_HOST="${VPS_HOST:-<your-user>@<your-vps-host>}"
VPS_APP_DIR="${VPS_APP_DIR:-/home/admin/apps/d20}"
PUBLIC_BASE="${PUBLIC_BASE:-https://agentdungeon.com}"
MAX_TURN_SECONDS="${MAX_TURN_SECONDS:-90}"
SYNC_SOURCE="${SYNC_SOURCE:-1}"
BUILD="${BUILD:-1}"
SYNC_HERMES_AUTH="${SYNC_HERMES_AUTH:-0}"

CORE_FILES=(
  "dm-runtime/app/main.py"
  "dm-runtime/app/routers/turn.py"
  "dm-runtime/app/services/dm_profile.py"
  "dm-runtime/app/services/intent_router.py"
  "dm-runtime/app/services/narrator.py"
  "dm-runtime/app/services/synthesis.py"
  "dm-runtime/app/services/rules_client.py"
  "dm-runtime/app/contract.py"
  "dm-runtime/hermes-home/profiles/d20-dm/config.yaml"
  "scripts/validate_actual_dm_agent_turn.py"
)

log() { printf '\n[%s] %s\n' "$(date -Is)" "$*"; }
fail() { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }
run() { log "+ $*"; "$@"; }

cd "$LOCAL_ROOT"

log "Local syntax check for DM core files"
run python3 -m py_compile \
  dm-runtime/app/main.py \
  dm-runtime/app/routers/turn.py \
  dm-runtime/app/services/dm_profile.py \
  dm-runtime/app/services/intent_router.py \
  dm-runtime/app/services/narrator.py \
  dm-runtime/app/services/synthesis.py \
  dm-runtime/app/services/rules_client.py \
  dm-runtime/app/contract.py \
  scripts/validate_actual_dm_agent_turn.py

log "Local core file fingerprint"
python3 - <<'PY'
from pathlib import Path
import hashlib
files = [
  "dm-runtime/app/main.py",
  "dm-runtime/app/routers/turn.py",
  "dm-runtime/app/services/dm_profile.py",
  "dm-runtime/app/services/intent_router.py",
  "dm-runtime/app/services/narrator.py",
  "dm-runtime/app/services/synthesis.py",
  "dm-runtime/app/services/rules_client.py",
  "dm-runtime/app/contract.py",
  "dm-runtime/hermes-home/profiles/d20-dm/config.yaml",
  "scripts/validate_actual_dm_agent_turn.py",
]
for rel in files:
    p = Path(rel)
    print(hashlib.sha256(p.read_bytes()).hexdigest(), rel)
PY

if [[ "$SYNC_SOURCE" == "1" ]]; then
  log "Sync source/build core files to VPS (excluding runtime-owned Hermes sessions/logs/db)"
  tmp_tar="/tmp/d20-dm-core-sync-$$.tar.gz"
  tar czf "$tmp_tar" \
    docker-compose.yml \
    dm-runtime/app \
    dm-runtime/requirements.txt \
    dm-runtime/Dockerfile \
    dm-runtime/docker-entrypoint.sh \
    dm-runtime/.dockerignore \
    dm-runtime/hermes-home/config.yaml \
    dm-runtime/hermes-home/SOUL.md \
    dm-runtime/hermes-home/profiles/d20-dm/config.yaml \
    dm-runtime/hermes-home/profiles/d20-dm/SOUL.md \
    scripts/validate_actual_dm_agent_turn.py \
    scripts/d20_dm_watchdog.sh
  cat "$tmp_tar" | ssh -o BatchMode=yes -o ConnectTimeout=10 "$VPS_HOST" "cd '$VPS_APP_DIR' && sudo tar xzf - --overwrite && sudo chown -R root:root dm-runtime/app dm-runtime/requirements.txt dm-runtime/Dockerfile dm-runtime/docker-entrypoint.sh dm-runtime/.dockerignore dm-runtime/hermes-home/config.yaml dm-runtime/hermes-home/SOUL.md dm-runtime/hermes-home/profiles/d20-dm/config.yaml dm-runtime/hermes-home/profiles/d20-dm/SOUL.md scripts/validate_actual_dm_agent_turn.py scripts/d20_dm_watchdog.sh docker-compose.yml || true"
  rm -f "$tmp_tar"
fi

if [[ "$SYNC_HERMES_AUTH" == "1" ]]; then
  [[ -f "$HOME/.hermes/auth.json" ]] || fail "SYNC_HERMES_AUTH=1 but ~/.hermes/auth.json is missing"
  log "Install host Hermes auth into VPS DM runtime build context and running container"
  tmp_auth="/tmp/d20-hermes-auth-$$.json"
  python3 - "$HOME/.hermes/auth.json" "$tmp_auth" <<'PY'
import json, sys
src=json.load(open(sys.argv[1]))
entry=(src.get('credential_pool') or {}).get('kimi-coding') or []
if not entry:
    raise SystemExit('No kimi-coding credential_pool entry in local Hermes auth.json')
# Important: force source=manual so container env KIMI_API_KEY placeholders do not override the stored token.
out={
    'version': src.get('version', 1),
    'providers': {},
    'active_provider': 'kimi-coding',
    'credential_pool': {'kimi-coding': []},
}
for raw in entry:
    e=dict(raw)
    e['source']='manual'
    e['base_url']='https://api.kimi.com/coding'
    out['credential_pool']['kimi-coding'].append(e)
json.dump(out, open(sys.argv[2], 'w'), indent=2)
PY
  chmod 600 "$tmp_auth"
  scp -q "$tmp_auth" "$VPS_HOST:/tmp/d20-hermes-auth.json"
  ssh "$VPS_HOST" "sudo install -m 600 /tmp/d20-hermes-auth.json '$VPS_APP_DIR/dm-runtime/hermes-home/auth.json' && sudo install -m 600 /tmp/d20-hermes-auth.json '$VPS_APP_DIR/dm-runtime/hermes-home/profiles/d20-dm/auth.json' && docker cp /tmp/d20-hermes-auth.json d20-dm-runtime:/root/.hermes/auth.json 2>/dev/null || true && docker cp /tmp/d20-hermes-auth.json d20-dm-runtime:/root/.hermes/profiles/d20-dm/auth.json 2>/dev/null || true && rm -f /tmp/d20-hermes-auth.json"
  rm -f "$tmp_auth"
fi

log "VPS compile/build/bring-up"
ssh "$VPS_HOST" "cd '$VPS_APP_DIR' && set -Eeuo pipefail
python3 - <<'PY'
import ast
for path in [
 'dm-runtime/app/main.py',
 'dm-runtime/app/routers/turn.py',
 'dm-runtime/app/services/dm_profile.py',
 'dm-runtime/app/services/intent_router.py',
 'dm-runtime/app/services/narrator.py',
 'dm-runtime/app/services/synthesis.py',
 'dm-runtime/app/services/rules_client.py',
 'dm-runtime/app/contract.py',
 'scripts/validate_actual_dm_agent_turn.py',
]:
    ast.parse(open(path).read())
    print('ast_ok', path)
PY
sudo chmod -R u+rwX,go+rX dm-runtime/hermes-home || true
if [[ '$BUILD' == '1' ]]; then
  docker compose -f docker-compose.yml -f docker-compose.override.yml build d20-rules-server d20-dm-runtime
fi
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d d20-redis d20-rules-server d20-dm-runtime
sleep 8
docker compose -f docker-compose.yml -f docker-compose.override.yml ps -a
"

log "Verify deployed core fingerprints match local"
python3 - <<'PY' > /tmp/d20-dm-local-sha.txt
from pathlib import Path
import hashlib
files = [
  "dm-runtime/app/main.py",
  "dm-runtime/app/routers/turn.py",
  "dm-runtime/app/services/dm_profile.py",
  "dm-runtime/app/services/intent_router.py",
  "dm-runtime/app/services/narrator.py",
  "dm-runtime/app/services/synthesis.py",
  "dm-runtime/app/services/rules_client.py",
  "dm-runtime/app/contract.py",
  "dm-runtime/hermes-home/profiles/d20-dm/config.yaml",
]
for rel in files:
    print(hashlib.sha256(Path(rel).read_bytes()).hexdigest(), rel)
PY
ssh "$VPS_HOST" "cd '$VPS_APP_DIR' && python3 - <<'PY'
from pathlib import Path
import hashlib
files = [
  'dm-runtime/app/main.py',
  'dm-runtime/app/routers/turn.py',
  'dm-runtime/app/services/dm_profile.py',
  'dm-runtime/app/services/intent_router.py',
  'dm-runtime/app/services/narrator.py',
  'dm-runtime/app/services/synthesis.py',
  'dm-runtime/app/services/rules_client.py',
  'dm-runtime/app/contract.py',
  'dm-runtime/hermes-home/profiles/d20-dm/config.yaml',
]
for rel in files:
    print(hashlib.sha256(Path(rel).read_bytes()).hexdigest(), rel)
PY" > /tmp/d20-dm-vps-sha.txt
diff -u /tmp/d20-dm-local-sha.txt /tmp/d20-dm-vps-sha.txt || fail "VPS core file fingerprints differ from local"

log "Hermes/Kimi smoke test inside d20-dm-runtime container"
ssh "$VPS_HOST" "docker exec d20-dm-runtime sh -lc 'HERMES_HOME=/root/.hermes hermes chat -q '\''Respond with ONLY valid JSON: {\"scene\":\"ok\",\"npc_lines\":[],\"tone\":\"neutral\",\"choices_summary\":[]} '\'' -Q --profile d20-dm > /tmp/d20_hout 2>/tmp/d20_herr; rc=\$?; echo rc=\$rc; echo ---stdout---; head -c 1200 /tmp/d20_hout; echo; echo ---stderr---; head -c 400 /tmp/d20_herr; echo; exit \$rc'" || fail "Hermes smoke test failed inside d20-dm-runtime"

log "HTTP health"
ssh "$VPS_HOST" "curl -fsS --max-time 20 http://127.0.0.1:8610/dm/health | python3 -m json.tool | head -120"

log "Actual DM-agent turn validation"
run python3 scripts/validate_actual_dm_agent_turn.py --base "$PUBLIC_BASE" --max-turn-seconds "$MAX_TURN_SECONDS"

log "Recent runtime logs: check for fallback/errors"
ssh "$VPS_HOST" "docker logs --since 5m d20-dm-runtime 2>&1 | grep -E 'Hermes mode failed|DM narrator returned no output|API call failed|Traceback|ERROR|HTTP 404|HTTP 401' && exit 1 || true" || fail "Recent DM runtime logs contain narrator fallback/error signatures"

log "PASS: D20 DM runtime is up, core files match, Hermes produces JSON prose, and /dm/turn returns session-backed narration"
