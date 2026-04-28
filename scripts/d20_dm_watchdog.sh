#!/usr/bin/env bash
# D20 DM runtime watchdog: verify rules/redis/dm-runtime are up and recover the stack if not.
# Designed for VPS cron/systemd timers and pre-playtest gates. No external dependencies beyond docker/curl.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/admin/apps/d20}"
PUBLIC_BASE="${PUBLIC_BASE:-https://agentdungeon.com}"
LOG_FILE="${LOG_FILE:-/var/log/d20-dm-watchdog.log}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.override.yml)
CURL_TIMEOUT="${CURL_TIMEOUT:-8}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"

log() {
  local msg="$*"
  printf '[%s] %s\n' "$(date -Is)" "$msg" | tee -a "$LOG_FILE"
}

status_of() {
  docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$1" 2>/dev/null || true
}

healthy_container() {
  local name="$1"
  local status
  status="$(status_of "$name")"
  [[ "$status" == running\ healthy || "$status" == running\ no-healthcheck ]]
}

http_ok() {
  local url="$1"
  curl -fsS --max-time "$CURL_TIMEOUT" "$url" >/dev/null
}

recover_stack() {
  log "RECOVER: docker compose up d20-redis d20-rules-server d20-dm-runtime"
  cd "$APP_DIR"
  "${COMPOSE[@]}" up -d d20-redis d20-rules-server d20-dm-runtime 2>&1 | tee -a "$LOG_FILE"
  sleep "$WAIT_SECONDS"
}

main() {
  cd "$APP_DIR"

  local reasons=()
  healthy_container d20-redis || reasons+=("d20-redis not running/healthy: $(status_of d20-redis)")
  healthy_container d20-rules-server || reasons+=("d20-rules-server not running/healthy: $(status_of d20-rules-server)")
  healthy_container d20-dm-runtime || reasons+=("d20-dm-runtime not running/healthy: $(status_of d20-dm-runtime)")
  http_ok "http://127.0.0.1:8600/health" || reasons+=("local rules /health failed")
  http_ok "http://127.0.0.1:8610/dm/health" || reasons+=("local dm /dm/health failed")
  http_ok "${PUBLIC_BASE%/}/dm/health" || reasons+=("public dm /dm/health failed")

  if (( ${#reasons[@]} > 0 )); then
    log "DEGRADED: ${reasons[*]}"
    recover_stack
    reasons=()
    healthy_container d20-redis || reasons+=("d20-redis still unhealthy: $(status_of d20-redis)")
    healthy_container d20-rules-server || reasons+=("d20-rules-server still unhealthy: $(status_of d20-rules-server)")
    healthy_container d20-dm-runtime || reasons+=("d20-dm-runtime still unhealthy: $(status_of d20-dm-runtime)")
    http_ok "http://127.0.0.1:8600/health" || reasons+=("local rules /health still failed")
    http_ok "http://127.0.0.1:8610/dm/health" || reasons+=("local dm /dm/health still failed")
    http_ok "${PUBLIC_BASE%/}/dm/health" || reasons+=("public dm /dm/health still failed")

    if (( ${#reasons[@]} > 0 )); then
      log "FAILED: ${reasons[*]}"
      "${COMPOSE[@]}" ps -a 2>&1 | tee -a "$LOG_FILE" || true
      docker logs --tail=80 d20-dm-runtime 2>&1 | tee -a "$LOG_FILE" || true
      exit 1
    fi
    log "RECOVERED: D20 DM runtime stack healthy"
    exit 0
  fi

  log "OK: D20 DM runtime stack healthy"
}

main "$@"
