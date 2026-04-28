# AgentDungeon Domain Endpoint Verification — 2026-04-28T14:39:20Z

## Verdict

`https://agentdungeon.com` and `https://www.agentdungeon.com` are live and serving the D20 production stack. Core rules, DM runtime, portal, static pages, map, OpenAPI, character, action, and cadence endpoints all return successfully on the new domain.

## DNS / TLS routing

- `agentdungeon.com` NS: `amy.ns.cloudflare.com`, `rob.ns.cloudflare.com`.
- Apex A: `15.235.197.208`.
- `www.agentdungeon.com`: CNAME -> `agentdungeon.com`, resolves to `15.235.197.208`.
- HTTPS works on apex and www.

## Fix applied

Found one production hardcode in the app source:

```text
app/routers/characters.py: portal_url = "https://d20.holocronlabs.ai/..."
```

Patched it to generate the portal URL from the request host / forwarded host:

```python
proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
portal_url = f"{proto}://{host}/portal/{result['token']}/view"
```

Deployed to VPS by patching `/home/admin/apps/d20/app/routers/characters.py`, rebuilding `d20-rules-server`, and recreating the container.

Sub-agent reviewed the patch and marked it safe to deploy; caveat: trusted proxy header boundary should be maintained by Traefik/Cloudflare.

## Endpoint matrix

Both `https://agentdungeon.com` and `https://www.agentdungeon.com` returned 200/201 for:

- `GET /`
- `GET /demo`
- `GET /map`
- `GET /docs`
- `GET /health`
- `GET /dm/health`
- `GET /dm/contract`
- `GET /api/map/data`
- `GET /openapi.json`
- `GET /characters`
- `GET /cadence/status`
- `GET /favicon.ico`
- `POST /characters`
- `POST /characters/{id}/actions`
- `POST /dm/intent/analyze`
- `POST /dm/turn`
- `POST /portal/token`
- `GET /portal/{token}`
- `GET /portal/{token}/view`
- `GET /portal/{token}/state`
- `GET /portal/token/{token}/validate`

## Gate results on new domain

- `python3 scripts/validate_actual_dm_agent_turn.py --base https://agentdungeon.com --max-turn-seconds 120` -> PASS; session `20260428_143550_5cf6f6`.
- `SMOKE_RULES_URL=https://agentdungeon.com SMOKE_DM_URL=https://agentdungeon.com SMOKE_CLEANUP=1 python3 scripts/production_smoke_gate.py` -> 10/10 PASS.
- `SMOKE_RULES_URL=https://agentdungeon.com SMOKE_DM_URL=https://agentdungeon.com python3 -m pytest tests/test_smoke.py -q` -> 20 passed.

## URL migration cleanup

- App source now has zero text matches for `d20.holocronlabs.ai` under `app/`.
- Deployed container source now has zero text matches for `d20.holocronlabs.ai` under `/app/app` for `*.py`, `*.html`, `*.js`, `*.css`.
- Updated current runbooks/scripts defaults to `https://agentdungeon.com`:
  - `README.md`
  - `DEPLOYMENT.md`
  - `D20-DEPLOYMENT-KEYS.md`
  - `PLAYTEST-GUIDE.md`
  - `PLAYTEST-RUNBOOK.md`
  - `PLAYER-PORTAL-SPEC.md`
  - `scripts/deploy_dm_runtime.sh`
  - `scripts/d20_dm_watchdog.sh`
  - `scripts/d20_dm_bringup_audit.sh`
  - `scripts/validate_actual_dm_agent_turn.py`
  - `scripts/run_heartbeat.py`
  - `scripts/run_semantic_heartbeat.py`
  - `scripts/freeze_validation_probe.py`
  - `scripts/state_probe.py`
  - `scripts/xp_verification_probe.py`
  - `scripts/run_heartbeat_p0_retest.py`
  - `scripts/heartbeat_retest.py`

Historical reports/playtest transcripts still mention the old domain as historical evidence; those were not rewritten.
