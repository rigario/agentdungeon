"""Tests for character-state validation gates (task bff2ef9f)."""

import sys
import os
import uuid
from unittest.mock import AsyncMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Unit tests — mocked characters and combat check
# ---------------------------------------------------------------------------

from app.services import character_validation as cv


class TestCharacterValidationUnit:
    """Pure validation logic unit tests."""

    def test_valid_character_passes(self):
        char = {"id": "c1", "hp_current": 25, "hp_max": 30, "is_archived": 0}
        result = cv.validate_char_state(char, check_combat=False)
        assert result["valid"] is True
        assert result["reason"] is None
        assert "alive" in result["checks_run"]

    def test_dead_character_fails(self):
        char = {"id": "c-dead", "hp_current": 0, "hp_max": 20, "is_archived": 0}
        result = cv.validate_char_state(char, check_combat=False)
        assert result["valid"] is False and result["code"] == "character_deceased"

    def test_negative_hp_fails(self):
        char = {"id": "c-neg", "hp_current": -5, "hp_max": 15, "is_archived": 0}
        result = cv.validate_char_state(char, check_combat=False)
        assert result["valid"] is False and result["code"] == "character_deceased"

    def test_archived_fails(self):
        char = {"id": "c-arc", "hp_current": 10, "hp_max": 10, "is_archived": 1}
        result = cv.validate_char_state(char, check_combat=False)
        assert result["valid"] is False and result["code"] == "character_archived"

    def test_combat_active_fails(self, monkeypatch):
        char = {"id": "c-fight", "hp_current": 10, "hp_max": 10, "is_archived": 0}
        monkeypatch.setattr(cv, "_has_active_combat", lambda cid: True)
        result = cv.validate_char_state(char, check_combat=True)
        assert result["valid"] is False and result["code"] == "combat_active"

    def test_combat_skip_when_disabled(self, monkeypatch):
        char = {"id": "c-fight", "hp_current": 10, "hp_max": 10, "is_archived": 0}
        monkeypatch.setattr(cv, "_has_active_combat", lambda cid: True)
        result = cv.validate_char_state(char, check_combat=False)
        assert result["valid"] is True  # skipped

    def test_missing_id_fails(self):
        char = {"hp_current": 10, "hp_max": 10, "is_archived": 0}
        result = cv.validate_char_state(char, check_combat=True)
        assert result["valid"] is False and result["code"] == "missing_id"


# ---------------------------------------------------------------------------
# Integration tests — mock DB row and active-combat query
# ---------------------------------------------------------------------------

class TestCharacterValidationDBMock:
    """Integration-style tests with mocked DB returns."""

    def test_live_character_from_db(self, monkeypatch):
        """validate_for_turn with DB mock returning live character."""
        mock_row = {
            "id": "char-live",
            "hp_current": 20,
            "hp_max": 20,
            "is_archived": 0,
        }

        captured = {}

        def mock_get_row(cid):
            captured["called_with"] = cid
            return mock_row

        monkeypatch.setattr(cv, "_get_character_row", mock_get_row)
        # _has_active_combat not called since check_combat=True needs check but character ok
        result = cv.validate_for_turn("char-live", check_combat=True)
        assert result["valid"] is True
        assert captured["called_with"] == "char-live"
        assert "alive" in result["checks_run"]
        assert "not_in_combat" in result["checks_run"]  # called _has_active_combat too

    def test_dead_character_from_db(self, monkeypatch):
        mock_row = {"id": "char-dead-db", "hp_current": 0, "hp_max": 15, "is_archived": 0}
        monkeypatch.setattr(cv, "_get_character_row", lambda cid: mock_row)
        result = cv.validate_for_turn("char-dead-db", check_combat=False)
        assert result["valid"] is False and result["code"] == "character_deceased"

    def test_combat_active_from_db(self, monkeypatch):
        mock_row = {"id": "c1", "hp_current": 5, "hp_max": 10, "is_archived": 0}
        monkeypatch.setattr(cv, "_get_character_row", lambda cid: mock_row)
        monkeypatch.setattr(cv, "_has_active_combat", lambda cid: True)
        result = cv.validate_for_turn("c1", check_combat=True)
        assert result["valid"] is False and result["code"] == "combat_active"

    def test_non_existent_character(self):
        """No DB row → not found."""
        result = cv.validate_for_turn("does-not-exist", check_combat=False)
        assert result["valid"] is False and result["code"] == "character_not_found"
