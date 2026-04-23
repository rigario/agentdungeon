"""Character validation gates — ensure character state is valid before turn processing.

This service centralizes pre-action and pre-turn validation checks that
must pass before the server mutates state or the DM narrates outcomes.

Validation rules (current scope):
  • Character must exist (caller ensures)
  • Character must not be archived
  • Character must be alive (hp_current > 0)
  • Character must not be in active combat (non-combat action path)

Future extensions (deferred):
  • Quest flag prerequisites, resource constraints, approval gate integration
"""

from __future__ import annotations

import sqlite3
from typing import Optional, Dict, Any, List
from app.services.database import get_db


class CharacterValidationError(ValueError):
    """Raised when character state fails pre-turn validation."""
    def __init__(self, reason: str, code: str = "invalid_character_state"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _get_character_row(character_id: str) -> Optional[sqlite3.Row]:
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    conn.close()
    return row


def _has_active_combat(character_id: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM combats WHERE character_id = ? AND status = 'active'",
        (character_id,)
    ).fetchone()
    conn.close()
    return row is not None


def validate_char_state(char: Dict[str, Any], check_combat: bool = True) -> Dict[str, Any]:
    """Validate character dict state before turn/action processing.

    Args:
        char: Character dict from DB (must include hp_current, hp_max, is_archived).
        check_combat: If True, also check that character not in active combat.

    Returns: {"valid": bool, "reason": str|None, "code": str|None, "checks_run": List[str]}
    """
    checks_run: List[str] = []

    if char.get("is_archived"):
        return {
            "valid": False,
            "reason": f"Character {char.get('id')} is archived. Restore before acting.",
            "code": "character_archived",
            "checks_run": checks_run,
        }
    checks_run.append("not_archived")

    hp_current = int(char.get("hp_current", 0))
    hp_max = int(char.get("hp_max", 1))
    if hp_current <= 0:
        return {
            "valid": False,
            "reason": f"Character is dead (HP: {hp_current}/{hp_max}). Cannot take actions.",
            "code": "character_deceased",
            "checks_run": checks_run,
        }
    checks_run.append("alive")

    if check_combat:
        character_id = char.get("id")
        if not character_id:
            return {"valid": False, "reason": "Character ID missing", "code": "missing_id", "checks_run": checks_run}
        if _has_active_combat(character_id):
            return {
                "valid": False,
                "reason": "Character is in active combat. Resolve combat before taking other actions.",
                "code": "combat_active",
                "checks_run": checks_run,
            }
        checks_run.append("not_in_combat")

    return {"valid": True, "reason": None, "code": None, "checks_run": checks_run}


def validate_for_turn(character_id: str, check_combat: bool = True) -> Dict[str, Any]:
    """Full validation including character fetch from DB."""
    char = _get_character_row(character_id)
    if char is None:
        return {
            "valid": False,
            "reason": f"Character not found: {character_id}",
            "code": "character_not_found",
            "checks_run": [],
        }
    return validate_char_state(dict(char), check_combat=check_combat)


def validate_or_raise(character_id: str, check_combat: bool = True) -> None:
    result = validate_for_turn(character_id, check_combat=check_combat)
    if not result["valid"]:
        raise CharacterValidationError(result["reason"], result["code"])
