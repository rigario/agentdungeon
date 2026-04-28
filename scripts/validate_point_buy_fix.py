#!/usr/bin/env python3
"""Standalone validation for point-buy fix (Task f77891b7).

Run: python3 scripts/validate_point_buy_fix.py
Exit code: 0 if all checks pass, 1 if any fail.
"""

import sys
import os

# Project root from script location = 2 levels up
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.services.srd_reference import (
    validate_point_buy, POINT_BUY_COSTS, POINT_BUY_BUDGET, generate_point_buy
)

def main():
    print("=== Point Buy Validation Fix Verification ===\n")

    # Check 1: Cost table
    expected_costs = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 6, 15: 9}
    if POINT_BUY_COSTS != expected_costs:
        print(f"FAIL: POINT_BUY_COSTS = {POINT_BUY_COSTS}")
        print(f"       Expected: {expected_costs}")
        return 1
    print(f"✓ POINT_BUY_COSTS correct: {POINT_BUY_COSTS}")

    if POINT_BUY_BUDGET != 27:
        print(f"FAIL: POINT_BUY_BUDGET = {POINT_BUY_BUDGET}, expected 27")
        return 1
    print(f"✓ POINT_BUY_BUDGET = 27")

    # Check 2: Exact 27-point enforcement
    test_cases = [
        # (stats dict, should_be_valid, description)
        ({"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}, False, "26 points (under)"),
        ({"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 9}, True,  "27 points (exact)"),
        ({"str": 15, "dex": 15, "con": 14, "int": 10, "wis": 10, "cha": 8}, False, "28 points (over)"),
        ({"str": 7,  "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}, False, "stat < 8"),
        ({"str": 16, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}, False, "stat > 15"),
        ({"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10},          False, "missing stat"),
    ]

    failures = []
    for stats, expected_valid, desc in test_cases:
        valid, msg = validate_point_buy(stats)
        if valid != expected_valid:
            failures.append(f"  ✗ {desc}: expected valid={expected_valid}, got valid={valid}, msg='{msg}'")
        else:
            print(f"✓ {desc}: correctly returned valid={valid}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f)
        return 1

    print("\n✅ All checks passed — point buy validation is 5E-compatible compliant")
    return 0

if __name__ == "__main__":
    sys.exit(main())
