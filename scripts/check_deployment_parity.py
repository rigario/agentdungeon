#!/usr/bin/env python3
"""
Deployment parity check for dm-runtime.
Verifies that local source, remote host files, and running container code
are in sync — no silent drift allowed.

Usage:
  python3 scripts/check_deployment_parity.py         # run full parity check

Exit codes:
  0 = all checks PASS
  1 = any check FAIL (mismatch, missing file, missing symbol)
"""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re


# ── Configuration ─────────────────────────────────────────────────────────────

LOCAL_ROOT = Path(os.environ.get("LOCAL_ROOT", Path.cwd()))
DEPLOY_HOST = os.environ.get("DEPLOY_HOST", "<your-user>@<host>")
DEPLOY_APP_DIR = Path(os.environ.get("DEPLOY_APP_DIR", "/path/to/agentdungeon"))
CONTAINER_NAME = "d20-dm-runtime"

# Files to verify under dm-runtime/app/
FILES_TO_CHECK = [
    "services/synthesis.py",
    "services/intent_router.py",
    "routers/turn.py",
    "main.py",
]

# Required symbols per file (function names that MUST exist)
REQUIRED_SYMBOLS: Dict[str, List[str]] = {
    "services/synthesis.py": [
        "_extract_trace",
        "_build_absurd_refusal",
        "synthesize_narration",
    ],
    "services/intent_router.py": [
        "_extract_error_status",
    ],
    # routers/turn.py and main.py have no critical-symbol requirements;
    # presence and SHA256 match suffice.
    "routers/turn.py": [],
    "main.py": [],
}

CONTAINER_APP_DIR = Path("/app/app")

def parse_args():
    parser = argparse.ArgumentParser(description="Deployment parity check for dm-runtime")
    parser.add_argument('--stage', choices=['all', 'local', 'remote', 'container'],
                        default='all',
                        help='Which stage(s) to run: local (baseline only), remote (remote host files), container (running container), all (default)')
    return parser.parse_args()




# ── Helpers ────────────────────────────────────────────────────────────────────

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def file_exists_via_ssh(remote_path: str) -> bool:
    result = subprocess.run(
        ["ssh", DEPLOY_HOST, f"test -f '{remote_path}' && echo yes || echo no"],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip() == "yes"


def read_file_via_ssh(remote_path: str) -> str:
    result = subprocess.run(
        ["ssh", DEPLOY_HOST, f"cat '{remote_path}'"],
        capture_output=True, timeout=15
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"Could not read {remote_path} on remote host")
    return result.stdout.decode("utf-8", errors="replace")


def read_file_from_container(container_path: str) -> str:
    result = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", container_path],
        capture_output=True, timeout=15
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"Could not read {container_path} in container")
    return result.stdout.decode("utf-8", errors="replace")


def symbol_in_file(content: str, symbol: str) -> bool:
    pattern = rf"(?:async\s+)?def\s+{re.escape(symbol)}\s*\("
    return bool(re.search(pattern, content))


def check_symbols(content: str, symbols: List[str], location: str) -> List[str]:
    missing = []
    for sym in symbols:
        if not symbol_in_file(content, sym):
            missing.append(f"  ✗ missing symbol: {sym}")
    return missing


def log(msg: str):
    print(f"[{subprocess.getoutput('date -Is')}] {msg}")


# ── Stage 1: Local source baseline ────────────────────────────────────────────

def stage_local_baseline() -> Tuple[Dict[str, str], Dict[str, bool], List[str]]:
    log("=== STAGE 1: Local source baseline ===")
    hashes: Dict[str, str] = {}
    symbols_ok: Dict[str, bool] = {}
    errors: List[str] = []

    for rel in FILES_TO_CHECK:
        local_path = LOCAL_ROOT / "dm-runtime" / "app" / rel
        if not local_path.exists():
            errors.append(f"  ✗ local file missing: {local_path}")
            continue

        sha = sha256_of_file(local_path)
        hashes[rel] = sha
        log(f"  ✓ {rel} — sha256: {sha[:12]}...")

        content = local_path.read_text()
        req_syms = REQUIRED_SYMBOLS.get(rel, [])
        if req_syms:
            missing = check_symbols(content, req_syms, f"local:{rel}")
            if missing:
                errors.append(f"  ✗ local symbol check FAIL for {rel}:\n" + "\n".join(missing))
                symbols_ok[rel] = False
            else:
                log(f"    ✓ symbols OK: {', '.join(req_syms)}")
                symbols_ok[rel] = True
        else:
            symbols_ok[rel] = True

    if errors:
        log("LOCAL BASELINE FAILED:")
        for e in errors:
            log(e)
        sys.exit(1)

    log("LOCAL BASELINE PASSED\n")
    return hashes, symbols_ok, errors


# ── Stage 2: remote host file parity ─────────────────────────────────────────────

def stage_remote_parity(local_hashes: Dict[str, str]) -> bool:
    log("=== STAGE 2: remote host file parity ===")
    all_ok = True

    for rel in FILES_TO_CHECK:
        remote_path = f"{DEPLOY_APP_DIR}/dm-runtime/app/{rel}"

        if not file_exists_via_ssh(remote_path):
            log(f"  ✗ remote host file missing: {remote_path}")
            all_ok = False
            continue

        try:
            remote_content = read_file_via_ssh(remote_path)
        except FileNotFoundError as e:
            log(f"  ✗ cannot read remote host file: {e}")
            all_ok = False
            continue

        remote_sha = hashlib.sha256(remote_content.encode("utf-8")).hexdigest()
        local_sha = local_hashes[rel]

        if remote_sha != local_sha:
            log(f"  ✗ HASH MISMATCH for {rel}")
            log(f"    local:  {local_sha[:12]}...")
            log(f"    remote:    {remote_sha[:12]}...")
            all_ok = False
        else:
            log(f"  ✓ {rel} — sha256 MATCH")

        req_syms = REQUIRED_SYMBOLS.get(rel, [])
        if req_syms:
            missing = check_symbols(remote_content, req_syms, f"remote:{rel}")
            if missing:
                log(f"  ✗ remote host symbol check FAIL for {rel}:\n" + "\n".join(missing))
                all_ok = False
            else:
                log(f"    ✓ remote host symbols OK: {', '.join(req_syms)}")

    if all_ok:
        log("REMOTE HOST PARITY PASSED\n")
    else:
        log("REMOTE HOST PARITY FAILED\n")
    return all_ok


# ── Stage 3: Container file parity ────────────────────────────────────────────

def stage_container_parity(local_hashes: Dict[str, str]) -> bool:
    log("=== STAGE 3: Container file parity ===")
    all_ok = True

    for rel in FILES_TO_CHECK:
        container_path = f"{CONTAINER_APP_DIR}/{rel}"

        try:
            container_content = read_file_from_container(container_path)
        except FileNotFoundError:
            log(f"  ✗ container file missing: {container_path}")
            all_ok = False
            continue

        container_sha = hashlib.sha256(container_content.encode("utf-8")).hexdigest()
        local_sha = local_hashes[rel]

        if container_sha != local_sha:
            log(f"  ✗ CONTAINER HASH MISMATCH for {rel}")
            log(f"    local:    {local_sha[:12]}...")
            log(f"    container:{container_sha[:12]}...")
            all_ok = False
        else:
            log(f"  ✓ {rel} — container sha256 MATCH")

        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "python3", "-m", "py_compile", f"/app/{rel}"],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            log(f"  ✗ container py_compile FAIL for {rel}")
            log(f"    stderr: {result.stderr.decode()[:200]}")
            all_ok = False
        else:
            log(f"    ✓ container py_compile OK")

    if all_ok:
        log("CONTAINER PARITY PASSED\n")
    else:
        log("CONTAINER PARITY FAILED\n")
    return all_ok


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    allowed = []
    if args.stage == 'local':
        allowed = ['local']
    elif args.stage == 'remote':
        allowed = ['local', 'remote']
    elif args.stage == 'container':
        allowed = ['local', 'container']
    else:  # all
        allowed = ['local', 'remote', 'container']

    log("Deployment Parity Check — dm-runtime")
    log(f"Stage(s):     {args.stage}")
    log(f"Local root:   {LOCAL_ROOT}")
    log(f"Remote host:     {DEPLOY_HOST}")
    log(f"Remote app dir:  {DEPLOY_APP_DIR}")
    log(f"Container:    {CONTAINER_NAME}")
    log(f"Files:        {', '.join(FILES_TO_CHECK)}")
    log("")

    local_hashes = {}
    local_symbols_ok = {}
    errors = []

    # Stage 1: always needed (provides hashes for comparison)
    if 'local' in allowed:
        local_hashes, local_symbols_ok, errors = stage_local_baseline()
    else:
        # Still need hashes for remote host/container comparison; compute silently
        local_hashes, local_symbols_ok, errors = stage_local_baseline()
        log("[local baseline computed — not validated — stage: {}]".format(args.stage))

    # Stage 2: remote host files
    remote_ok = True
    if 'remote' in allowed:
        remote_ok = stage_remote_parity(local_hashes)

    # Stage 3: Container files
    container_ok = True
    if 'container' in allowed:
        container_ok = stage_container_parity(local_hashes)

    log("=== FINAL RESULT ===")
    success = True
    if 'remote' in allowed and not remote_ok:
        success = False
    if 'container' in allowed and not container_ok:
        success = False

    if success:
        log("✓ PARITY CHECK PASSED")
        if args.stage == 'local':
            log("Local baseline validated.")
        elif args.stage == 'remote':
            log("Remote host files verified against local source.")
        elif args.stage == 'container':
            log("Container files verified against local source.")
        else:
            log("Deployment parity verified: local ↔ remote host ↔ container")
        sys.exit(0)
    else:
        log("✗ PARITY CHECK FAILED")
        log("Review the mismatches above and re-deploy.")
        sys.exit(1)


if __name__ == "__main__":
    main()
