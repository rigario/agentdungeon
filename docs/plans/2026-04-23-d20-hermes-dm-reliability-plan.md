# D20 Hermes DM Reliability Plan

> For Hermes: use subagent-driven-development for implementation, with Alpha final verification before deploy.

Goal: Make the D20 DM a reliable Hermes-backed narrator running inside the VPS Docker deployment, with strict isolation, deterministic startup, real health checks, and end-to-end validated turn flow.

Architecture:
- Keep the public API as `/dm/*` on the dm-runtime service.
- Keep Hermes private/internal to the dm-runtime container.
- Remove dependence on the VPS host `~/.hermes` mount and host symlinked Hermes binary.
- Bake a dedicated D20-only Hermes runtime + profile into the container image.
- Persist only D20 DM session state in a dedicated volume/store.

Tech stack: FastAPI, Docker Compose, Hermes CLI, Kimi Coding API, Redis, Traefik.

---

## Verified current-state facts

1. `d20-dm-runtime` is localhost-bound on the VPS (`127.0.0.1:8610`), not directly public.
2. `d20-dm-runtime` currently mounts `/home/admin/.hermes` into `/root/.hermes` read-only.
3. `d20-dm-runtime` currently mounts `/home/admin/.local/bin/hermes` into `/usr/local/bin/hermes`.
4. The mounted Hermes binary is a host symlink pointing to `/home/admin/.hermes/hermes-agent/venv/bin/hermes`.
5. Inside the container, `/usr/local/bin/hermes` exists but is not executable at runtime (`/usr/local/bin/hermes: not found`) because the symlink target and shebang interpreter do not exist in the container.
6. `DM_HERMES_MODE=hermes` is set in the running container, but the actual Hermes CLI path is broken.
7. The `d20-dm` profile on the VPS host is misconfigured for current Kimi usage:
   - model default is `kimi-k2.5`
   - provider base URL is `https://api.kimi.com/coding`
   - this should be `kimi-for-coding` and `https://api.kimi.com/coding/v1`
8. There is still a stale localhost-only container on port `8611` (`goofy_meninsky`).
9. Live DM failures currently happen before narration on fresh characters because rules-server world data is inconsistent (`Location not found: thornhold`).

---

## Required outcome

A deployment is only considered correct when all of the following are true:

- `d20-dm-runtime` starts without any host Hermes bind-mounts.
- `hermes chat -q ... -Q --profile d20-dm` works inside the container.
- `/dm/health` verifies actual Hermes usability, not just env var presence.
- `/dm/turn` can complete a full successful request for a valid character and location.
- Session continuity works across turns using a D20-only session mapping.
- No public route exposes raw Hermes access.
- No container has access to host-global Hermes sessions/auth/config unrelated to D20.

---

## Phase 1 — Fix the architecture boundary

### Task 1: Remove host-global Hermes home mount

Objective: Stop sharing `/home/admin/.hermes` with the dm container.

Files:
- Modify: `/home/admin/apps/d20/docker-compose.yml`
- Modify: `/home/rigario/Projects/rigario-d20/docker-compose.yml`

Change:
- Remove:
  - `/home/admin/.hermes:/root/.hermes:ro`
  - `/home/admin/.local/bin/hermes:/usr/local/bin/hermes:ro`

Replace with either:
- a container-local baked runtime, or
- a dedicated D20-only volume such as `/home/admin/apps/d20/hermes-home:/root/.hermes`

Success criteria:
- `docker inspect d20-dm-runtime` shows no mount from `/home/admin/.hermes`
- `docker exec d20-dm-runtime ls -la /root/.hermes` shows only D20-specific content

### Task 2: Bake Hermes into the dm image

Objective: Make Hermes runnable inside the container without relying on host symlinks.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/Dockerfile`
- Modify: `/home/admin/apps/d20/rules-server/dm-runtime/Dockerfile` after deploy sync

Implementation requirements:
- Install Hermes inside the image from a known-good source, not via host mount.
- Ensure the final binary path is real inside the image, not a symlink to a host path.
- Ensure the Python interpreter referenced by the Hermes entrypoint exists in-container.

Success criteria:
- `docker exec d20-dm-runtime which hermes` returns a valid in-image path
- `docker exec d20-dm-runtime hermes --help` exits 0

### Task 3: Create a dedicated D20-only Hermes home

Objective: Make the DM use its own isolated Hermes state.

Files:
- Create or populate inside image/volume:
  - `/root/.hermes/config.yaml`
  - `/root/.hermes/auth.json`
  - `/root/.hermes/profiles/d20-dm/config.yaml`
  - `/root/.hermes/profiles/d20-dm/SOUL.md`
  - `/root/.hermes/profiles/d20-dm/GOAL.md`

Implementation requirements:
- Explicitly set `HERMES_HOME=/root/.hermes`
- Do not copy unrelated profiles/sessions/skills from the host-global Hermes home
- Only include what the DM needs

Success criteria:
- `docker exec d20-dm-runtime env | grep HERMES_HOME` shows `/root/.hermes`
- `docker exec d20-dm-runtime ls /root/.hermes/profiles` shows only intended D20 profiles

---

## Phase 2 — Fix profile and model configuration

### Task 4: Preserve the intended Kimi provider wiring while validating it in-container

Objective: Keep the D20 profile aligned with the intended Kimi Coding provider/key pair, and only change model/base_url if the in-container Hermes smoke test proves it is wrong.

Files:
- Modify if needed: `/root/.hermes/profiles/d20-dm/config.yaml` in container build source

Requirements:
- Start from the currently intended `kimi-coding` provider configuration.
- Treat the model/base URL as user-validated unless a direct in-container `hermes chat ... --profile d20-dm` smoke test proves otherwise.
- Focus first on making Hermes runnable and isolated; do not churn provider config without evidence.

Success criteria:
- A direct `hermes chat -q ... -Q --profile d20-dm` call succeeds inside the container.
- If it fails, capture the exact error before changing model/base_url.

### Task 5: Tighten the D20 profile scope

Objective: Keep the DM capable, but only within its game lane.

Files:
- Modify: `d20-dm` profile config and prompt files

Requirements:
- No browser
- No broad terminal access for runtime narration path
- No memory providers beyond D20 session continuity if needed
- Only D20-specific tools/files if any tools are enabled
- If no tools are actually needed for narration, keep toolsets minimal

Success criteria:
- The DM can narrate turns but cannot access unrelated host context

---

## Phase 3 — Fix dm-runtime integration logic

### Task 6: Replace fake health with real Hermes readiness check

Objective: `/dm/health` must verify actual narratability.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/routers/turn.py`
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/services/dm_profile.py`

Implementation requirements:
- Add a lightweight readiness function in `dm_profile.py` that checks:
  - Hermes binary exists and is executable
  - profile exists
  - optional one-shot smoke command with short timeout
- Health endpoint should report:
  - `binary_ok`
  - `profile_ok`
  - `smoke_ok`
  - `mode`
  - `model`

Current bad behavior:
- health only reports env/config presence and can say "healthy" while Hermes is unusable

Success criteria:
- break the Hermes binary and health goes degraded
- fix it and health goes healthy

### Task 7: Make Hermes invocation deterministic and robust

Objective: Ensure `narrate_via_hermes` is production-grade.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/services/dm_profile.py`

Required changes:
- Preflight check `shutil.which("hermes")`
- Explicit timeout handling
- Parse session ID from stderr
- Parse content from stdout only
- Strip resume preamble lines
- Replace fragile regex-only JSON extraction with robust parser strategy:
  1. try full JSON parse
  2. if wrapped, extract fenced block or largest balanced JSON object
- Add structured logging for subprocess return code, timeout, stderr summary

Success criteria:
- one-shot narration succeeds reliably
- malformed output degrades cleanly to passthrough without crashing

### Task 8: Add DM session continuity

Objective: Preserve story continuity across turns.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/routers/turn.py`
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/services/dm_profile.py`
- Create: `/home/rigario/Projects/rigario-d20/dm-runtime/app/services/session_store.py`

Requirements:
- Persist `character_id -> hermes_session_id`
- Prefer Redis or a dedicated small SQLite DB under dm-runtime ownership
- On first turn: create session
- On subsequent turns: `--resume` previous session
- Reset or rotate session when character/campaign requires it

Success criteria:
- two consecutive turns for the same character use the same Hermes session
- logs prove resume path is being used

---

## Phase 4 — Separate Hermes reliability from rules-server reliability

### Task 9: Fix the fresh-character world-state failure

Objective: Make the DM able to complete a normal turn for a newly created character.

Files:
- Investigate and likely modify rules-server files under `/home/rigario/Projects/rigario-d20/app/`
- Investigate seed/world data and character creation defaults

Current verified failure:
- new characters spawn at `thornhold`
- rules-server returns `404 Location not found: thornhold` for actions/turns

This is not a Hermes bug, but it currently blocks reliable DM success.

Success criteria:
- create character
- POST `/dm/turn` with an exploration prompt
- return 200 end-to-end

### Task 10: Add explicit degraded-mode behavior when rules-server fails

Objective: Avoid raw 502s where possible.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/routers/turn.py`
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/app/services/rules_client.py`

Requirements:
- Retry transient upstream failures
- Distinguish permanent game-state errors from transient infra errors
- Return a structured DM-facing degraded response for transient failures

Success criteria:
- transient upstream failure does not look like a hard crash to the player

---

## Phase 5 — Clean up deployment hygiene

### Task 11: Remove stale localhost-only container on 8611

Objective: Eliminate ambiguity and stale runtime paths.

Files:
- VPS deployment/runtime state

Action:
- remove `goofy_meninsky`
- verify no stale extra rules-server proxy container remains

Success criteria:
- `docker ps` shows only intended D20 containers

### Task 12: Make compose and image the single source of truth

Objective: Prevent future drift between repo and VPS deployment.

Files:
- `/home/rigario/Projects/rigario-d20/docker-compose.yml`
- `/home/admin/apps/d20/docker-compose.yml`
- deployment script(s)

Requirements:
- repo compose must match deployed compose
- no hidden manual host bind-mount dependencies
- deployment script must sync the correct `rules-server/dm-runtime` path

Success criteria:
- a fresh rebuild from repo reproduces the working deployment exactly

---

## Phase 6 — Add reliable verification

### Task 13: Add an explicit Hermes smoke test

Objective: Test the actual Hermes path, not just unit helpers.

Files:
- Create: `/home/rigario/Projects/rigario-d20/tests/test_dm_hermes_smoke.py`

Test should verify:
- Hermes binary exists in container/local env under test mode
- `d20-dm` profile exists
- a one-shot narration call returns parseable JSON with `scene`

### Task 14: Add strict DM end-to-end acceptance tests

Objective: Prove the full DM works, not just pieces.

Files:
- Modify: `/home/rigario/Projects/rigario-d20/tests/test_smoke.py`
- Modify: `/home/rigario/Projects/rigario-d20/dm-runtime/tests/test_e2e_dm_path.py`

Change test philosophy:
- stop treating `502` as acceptable for core DM turn tests
- for critical-path DM tests, `200` must be required once world-state is fixed

Acceptance path:
1. create character
2. dm health green with real Hermes smoke OK
3. dm turn explore -> 200
4. dm turn move/general -> 200
5. second turn resumes same Hermes session
6. combat path returns valid narrated output when encounter exists

---

## Final acceptance checklist

A production deployment is only accepted when all are true:

- [ ] No `/home/admin/.hermes` mount in dm container
- [ ] No host symlinked Hermes binary mount in dm container
- [ ] Hermes CLI baked into image and runnable in-container
- [ ] `d20-dm` profile uses `kimi-for-coding` and `/coding/v1`
- [ ] `/dm/health` verifies actual Hermes readiness
- [ ] Fresh character can complete a successful `/dm/turn`
- [ ] Session continuity works across turns
- [ ] No stale 8611 container
- [ ] Smoke tests cover Hermes path and strict end-to-end turn success

---

## Suggested execution order

1. Fix isolation boundary (remove host `.hermes` and host binary mounts)
2. Bake Hermes into image
3. Create dedicated D20-only Hermes home/profile
4. Correct model/base_url/profile config
5. Implement real health checks
6. Implement robust Hermes subprocess handling
7. Add session persistence
8. Fix rules-server spawn/world-state bug
9. Tighten tests and redeploy

---

## Verification commands after implementation

```bash
ssh admin@15.235.197.208 'docker inspect d20-dm-runtime --format "{{json .Mounts}}"'
ssh admin@15.235.197.208 'docker exec d20-dm-runtime which hermes'
ssh admin@15.235.197.208 'docker exec d20-dm-runtime hermes chat -q "Respond with exactly {\"ok\":true}" -Q --profile d20-dm'
curl -s https://d20.holocronlabs.ai/dm/health | jq .
curl -s -X POST https://d20.holocronlabs.ai/dm/character -H 'Content-Type: application/json' -d '{"name":"Smoke","race":"Human","class":"Fighter","background":"Soldier"}'
```

Expected:
- no host-global Hermes mounts
- Hermes binary runnable
- profile invocation succeeds
- health includes real readiness fields
- full DM turn path returns 200
