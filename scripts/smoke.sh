#!/bin/bash
# D20 VPS Smoke Test — validates all services are healthy
set -e

echo "=== D20 VPS Smoke Test ==="
echo ""

# 1. Rules server health
echo "[1/4] Rules server health check..."
RS_HEALTH=$(curl -sf http://localhost:8600/health 2>/dev/null || echo "FAIL")
if echo "$RS_HEALTH" | grep -q "healthy\|ok"; then
    echo "  PASS: Rules server is healthy"
else
    echo "  FAIL: Rules server — $RS_HEALTH"
fi

# 2. Redis health
echo "[2/4] Redis health check..."
REDIS_PING=$(docker exec d20-redis redis-cli ping 2>/dev/null || echo "FAIL")
if [ "$REDIS_PING" = "PONG" ]; then
    echo "  PASS: Redis is healthy"
else
    echo "  FAIL: Redis — $REDIS_PING"
fi

# 3. DM runtime health
echo "[3/4] DM runtime health check..."
DM_HEALTH=$(curl -sf http://localhost:8610/dm/health 2>/dev/null || echo "FAIL")
if echo "$DM_HEALTH" | grep -q "healthy\|ok"; then
    echo "  PASS: DM runtime is healthy"
else
    echo "  FAIL: DM runtime — $DM_HEALTH"
fi

# 4. Traefik ingress (if domain configured)
echo "[4/4] Traefik ingress check..."
DOMAIN="${D20_DOMAIN:-}"
if [ -n "$DOMAIN" ]; then
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "https://$DOMAIN/dm/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  PASS: Traefik ingress — https://$DOMAIN"
    else
        echo "  FAIL: Traefik ingress — HTTP $HTTP_CODE"
    fi
else
    echo "  SKIP: D20_DOMAIN not set"
fi

echo ""
echo "=== Smoke test complete ==="
