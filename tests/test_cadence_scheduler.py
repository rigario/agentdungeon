"""
Tests for cadence background scheduler.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, call

from app.services.cadence_scheduler import (
    tick_all_active_characters,
    start_scheduler,
    stop_scheduler,
    get_scheduler,
    set_enabled,
)
from app.services.playtest_cadence import set_cadence_mode


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Ensure clean scheduler state between tests."""
    stop_scheduler(None)
    set_enabled(True)
    yield
    stop_scheduler(None)


def cleanup_doom_clocks():
    """Remove all doom_clock test rows."""
    from app.services.database import get_db
    conn = get_db()
    conn.execute("DELETE FROM doom_clock WHERE character_id LIKE 'test_%'")
    conn.commit()
    conn.close()


def cleanup_characters():
    """Remove all test character rows."""
    from app.services.database import get_db
    conn = get_db()
    conn.execute("DELETE FROM characters WHERE id LIKE 'test_%'")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def cleanup_db():
    """Clean up test data after each test."""
    yield
    cleanup_doom_clocks()
    cleanup_characters()


def create_test_character(character_id: str):
    """Create a minimal character row required for FK constraint."""
    from app.services.database import get_db
    conn = get_db()
    conn.execute(
        """
        INSERT INTO characters (
            id, player_id, name, race, class, level,
            hp_current, hp_max, ac_value, ability_scores_json,
            location_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            "test_player",
            f"Test {character_id}",
            "Human",
            "Fighter",
            1,
            20,
            20,
            15,
            '{"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8}',
            "town-square",
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_tick_no_active_characters_when_mode_normal():
    """When cadence mode is 'normal' (is_active=0), tick function exits early."""
    tick_all_active_characters()  # should no-op without error


def test_tick_no_active_characters_when_playtest_but_no_doom_clocks():
    """When playtest active but no characters have doom clocks, exits cleanly."""
    set_cadence_mode("playtest", tick_interval=60)
    tick_all_active_characters()  # no exception
    set_cadence_mode("normal")


@patch('app.services.cadence_scheduler.advance_tick')
def test_tick_processes_all_active_characters(mock_advance_tick):
    """When active characters exist, advance_tick called for each."""
    char_ids = ["test_a", "test_b", "test_c"]
    
    # Create character rows first (FK constraint)
    for cid in char_ids:
        create_test_character(cid)
    
    # Create active doom clock rows
    from app.services.database import get_db
    conn = get_db()
    for cid in char_ids:
        conn.execute(
            "INSERT INTO doom_clock (character_id, total_ticks, portents_triggered, is_active) "
            "VALUES (?, 0, 0, 1)",
            (cid,),
        )
    conn.commit()
    conn.close()
    
    set_cadence_mode("playtest", tick_interval=60)
    tick_all_active_characters()
    
    assert mock_advance_tick.call_count == 3
    mock_advance_tick.assert_has_calls([call(cid) for cid in char_ids], any_order=True)
    
    set_cadence_mode("normal")


@patch('app.services.cadence_scheduler.advance_tick')
def test_tick_continues_on_individual_character_error(mock_advance_tick):
    """Errors on one character don't prevent ticking others."""
    char_ids = ["test_ok1", "test_fail", "test_ok2"]
    
    for cid in char_ids:
        create_test_character(cid)
    
    from app.services.database import get_db
    conn = get_db()
    for cid in char_ids:
        conn.execute(
            "INSERT INTO doom_clock (character_id, total_ticks, portents_triggered, is_active) "
            "VALUES (?, 0, 0, 1)",
            (cid,),
        )
    conn.commit()
    conn.close()
    
    mock_advance_tick.side_effect = lambda cid: (_ for _ in ()).throw(
        Exception("DB locked") if cid == "test_fail" else None
    )
    
    set_cadence_mode("playtest", tick_interval=60)
    tick_all_active_characters()
    
    assert mock_advance_tick.call_count == 3
    
    set_cadence_mode("normal")


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def test_scheduler_start_stop():
    """Scheduler can be started and stopped cleanly."""
    stop_scheduler(None)
    start_scheduler(None)
    
    scheduler = get_scheduler()
    assert scheduler is not None
    assert scheduler.running
    
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "cadence_tick_job"
    
    stop_scheduler(None)
    assert get_scheduler() is None


def test_scheduler_idempotent_start():
    """Starting an already-started scheduler is safe (no-op)."""
    start_scheduler(None)
    first = get_scheduler()
    start_scheduler(None)
    second = get_scheduler()
    assert first is second
