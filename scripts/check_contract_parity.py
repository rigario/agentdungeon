#!/usr/bin/env python3
"""
Contract manifest parity check — rules-server vs dm-runtime.

Exit codes:
  0 = all checks PASS
  1 = any check FAIL

Usage:
  python3 scripts/check_contract_parity.py
  python3 scripts/check_contract_parity.py --dry-run
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Set

PROJECT = Path("/home/rigario/Projects/rigario-d20")
RULES_DIR = PROJECT / "app"
DM_DIR    = PROJECT / "dm-runtime" / "app"

# ── Expected endpoints (full paths after router prefix) ─────────────────────────
EXPECTED = [
    # health router (no prefix)
    ("GET",    "/health"),
    # characters router (prefix="/characters")
    ("GET",    "/characters"),
    ("POST",   "/characters"),
    ("GET",    "/characters/{character_id}"),
    ("PATCH",  "/characters/{character_id}"),
    ("DELETE", "/characters/{character_id}"),
    # actions router (prefix="/characters/{character_id}")
    ("POST",   "/characters/{character_id}/actions"),
    # turn router (prefix="/characters/{character_id}/turn")
    ("POST",   "/characters/{character_id}/turn/start"),
    ("GET",    "/characters/{character_id}/turn/result/{turn_id}"),
    ("GET",    "/characters/{character_id}/turn/latest"),
    # combat router (prefix="/characters/{character_id}/combat")
    ("POST",   "/characters/{character_id}/combat/start"),
    ("POST",   "/characters/{character_id}/combat/act"),
    ("GET",    "/characters/{character_id}/combat"),
    ("POST",   "/characters/{character_id}/combat/flee"),
]

# ── Required symbols (function names) ──────────────────────────────────────────
REQUIRED_SYMBOLS = {
    "routers/actions.py": ["submit_action", "_resolve_move", "_resolve_combat"],
    "routers/turns.py":   ["start_turn", "get_latest_turn", "get_turn_result"],
    "routers/combat.py":  ["start_combat", "combat_act", "get_combat"],
    "services/database.py": ["get_db", "init_db"],
    "services/rules_client.py": ["submit_action", "start_turn", "get_character"],
    "services/intent_router.py": ["classify_intent", "_route_action"],
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_prefix(fp: Path) -> str:
    with open(fp) as f:
        m = re.search(r'APIRouter\(prefix=["\']([^"\']+)["\']', f.read())
    return m.group(1) if m else ""

def parse_routes(fp: Path) -> List[Tuple[str, str, str]]:
    """Return (method, full_path, function_name) for all routes in a router file."""
    try:
        with open(fp) as f:
            content = f.read()
    except Exception:
        return []

    prefix = get_prefix(fp)
    routes = []
    # decorator: @router.method("path", ...)
    deco_re = re.compile(r'@router\.(get|post|put|delete|patch)\("(.*?)"[^\)]*\)')
    func_re = re.compile(r'(?:async\s+)?def\s+(\w+)\s*\(')

    for m in deco_re.finditer(content):
        method   = m.group(1).upper()
        rel_path = m.group(2)
        after    = content[m.end():]
        fm       = func_re.search(after)
        if fm:
            full = prefix + rel_path
            routes.append((method, full, fm.group(1)))
    return routes

def symbol_missing(fp: Path, symbols: List[str]) -> List[str]:
    if not fp.exists():
        return [f"  FILE NOT FOUND: {fp}"]
    try:
        with open(fp) as f:
            content = f.read()
    except Exception as e:
        return [f"  CANNOT READ: {fp}: {e}"]
    miss = []
    for sym in symbols:
        if not re.search(rf'(?:async\s+)?def\s+{re.escape(sym)}\s*\(', content):
            miss.append(f"  MISSING SYMBOL: {sym} in {fp.name}")
    return miss

def log(msg: str):
    print(f"[contract-parity] {msg}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Contract parity check")
    parser.add_argument('--dry-run', action='store_true', help="List checks only")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — checks that would be performed:")
        print()
        print("Required endpoints:")
        for m, p in EXPECTED:
            print(f"  {m:7} {p}")
        print(f"\nTotal: {len(EXPECTED)} endpoints")
        print()
        print("Required symbols:")
        for rel, syms in REQUIRED_SYMBOLS.items():
            print(f"  {rel}: {', '.join(syms)}")
        return 0

    log("=== CONTRACT PARITY CHECK — rules-server / dm-runtime ===")
    print()

    # Phase 1 — discover routes
    log("Phase 1 — Scanning rules-server routers...")
    router_dir = RULES_DIR / "routers"
    all_routes: Set[Tuple[str, str]] = set()

    for rf in router_dir.glob("*.py"):
        for method, full_path, _func in parse_routes(rf):
            all_routes.add((method, full_path))

    log(f"  Found {len(all_routes)} routes across {len(list(router_dir.glob('*.py')))} router files")
    # Debug relevant subset
    relevant = sorted([r for r in all_routes if 'char' in r[1].lower() or r[1] in ['/health']])
    for m, p in relevant:
        log(f"  {m:7} {p}")
    print()

    # Phase 2 — endpoint existence
    log("Phase 2 — Verifying required HTTP endpoints...")
    missing = []
    for method, path in EXPECTED:
        if (method, path) not in all_routes:
            missing.append(f"  MISSING: {method} {path}")
    if missing:
        for m in missing:
            log(m)
        route_ok = False
    else:
        log("All required endpoints present")
        print()
        route_ok = True

    # Phase 3 — required symbols
    log("Phase 3 — Verifying required symbols in critical files...")
    sym_errors = []
    for rel, symbols in REQUIRED_SYMBOLS.items():
        if rel.startswith("routers/"):
            base = RULES_DIR
        elif rel.startswith("services/rules_client"):
            base = DM_DIR
        elif "intent_router" in rel:
            base = DM_DIR
        else:
            base = RULES_DIR
        fp = base / rel
        sym_errors.extend(symbol_missing(fp, sym_errors))
    if sym_errors:
        for e in sym_errors:
            log(e)
        sym_ok = False
    else:
        log("All required symbols present")
        print()
        sym_ok = True

    # Phase 4 — contract version
    log("Phase 4 — Verifying contract version exists...")
    contract_file = DM_DIR / "contract.py"
    ver_ok = contract_file.exists()
    if ver_ok:
        txt = contract_file.read_text()
        vm = re.search(r'CONTRACT_VERSION\s*=\s*"([^"]+)"', txt)
        if vm:
            log(f"  dm-runtime contract version: {vm.group(1)}")
            print()
        else:
            ver_ok = False
            log("  CONTRACT_VERSION not found in contract.py")
            print()

    # Summary
    log("=== FINAL RESULT ===")
    if route_ok and sym_ok and ver_ok:
        log("CONTRACT PARITY CHECK PASSED")
        log("  Rules-server API matches dm-runtime contract expectations.")
        return 0
    else:
        log("CONTRACT PARITY CHECK FAILED")
        log("  Review gaps above and update rules-server or dm-runtime contract.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
