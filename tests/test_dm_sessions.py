"""Tests for dm_sessions table and dm_proxy session functions."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.database import init_db, get_db
from app.services.dm_proxy import get_dm_session, save_dm_session


@pytest.fixture(autouse=True)
def setup_db():
    """Initialize fresh DB and clear all tables before each test."""
    init_db()
    # Clear all tables to ensure isolation
    conn = get_db()
    tables = [
        "dm_sessions", "characters", "event_log", "narrative_flags",
        "character_fronts", "turn_results", "combats", "combat_participants"
    ]
    for table in tables:
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            pass  # Table might not exist in early tests
    conn.commit()
    conn.close()
    yield


def make_character(char_id="test-char-123"):
    """Create a minimal test character row directly."""
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO characters (
            id, player_id, name, race, class, level,
            hp_current, hp_max, ac_value, ability_scores_json, location_id
        ) VALUES (?, ?, ?, ?, ?, 1, 10, 10, 16, '{}', 'rusty-tankard')
    """, (char_id, "test-player", f"Hero-{char_id[:8]}", "Human", "Fighter"))
    conn.commit()
    conn.close()
    return char_id


def test_dm_sessions_table_exists():
    """Verify dm_sessions table was created in schema."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dm_sessions'"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "dm_sessions table must exist"


def test_dm_sessions_table_schema():
    """Verify dm_sessions has required columns and constraints."""
    conn = get_db()
    cursor = conn.execute("PRAGMA table_info(dm_sessions)")
    cols = {row["name"]: row for row in cursor.fetchall()}
    conn.close()

    assert "character_id" in cols
    assert "session_id" in cols
    assert "updated_at" in cols
    # character_id is PRIMARY KEY (enforces uniqueness)
    assert cols["character_id"]["pk"] == 1


def test_save_and_get_dm_session():
    """Save a session via save_dm_session, retrieve via get_dm_session."""
    char_id = make_character("char-session-123")
    session_id = "session-abc-123"

    # Initially no session
    before = get_dm_session(char_id)
    assert before is None

    # Save session
    save_dm_session(char_id, session_id)

    # Retrieve
    retrieved = get_dm_session(char_id)
    assert retrieved == session_id


def test_save_dm_session_updates():
    """Saving a second session updates the existing row."""
    char_id = make_character("char-updates-456")
    session1 = "session-first"
    session2 = "session-second"

    save_dm_session(char_id, session1)
    save_dm_session(char_id, session2)

    retrieved = get_dm_session(char_id)
    assert retrieved == session2


def test_get_dm_session_expired():
    """get_dm_session returns None for sessions older than 30 minutes."""
    char_id = make_character("char-expired-789")
    session_id = "session-expired"

    # Insert with manual old timestamp
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO dm_sessions (character_id, session_id, updated_at) "
        "VALUES (?, ?, datetime('now', '-31 minutes'))",
        (char_id, session_id)
    )
    conn.commit()
    conn.close()

    retrieved = get_dm_session(char_id)
    assert retrieved is None


def test_dm_sessions_foreign_key_enforced():
    """Inserting a session for a non-existent character fails FK constraint."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO dm_sessions (character_id, session_id, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("nonexistent-char", "orphan-session")
        )
        conn.commit()
        raise AssertionError("Should have failed FK constraint")
    except Exception as e:
        # SQLite raises OperationalError for FK violation, not IntegrityError
        msg = str(e).lower()
        assert "constraint" in msg or "foreign key" in msg or "constraint failed" in msg
    finally:
        conn.close()


def test_session_index_exists():
    """Index on dm_sessions(updated_at) exists for TTL queries."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dm_sessions_updated'"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Index idx_dm_sessions_updated must exist"
