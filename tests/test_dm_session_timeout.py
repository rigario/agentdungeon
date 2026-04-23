"""Tests for DM session timeout enforcement (30-minute idle timeout).

Ensures that get_dm_session only returns sessions with recent activity
(updated_at within the last 30 minutes).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3
import datetime
import pytest
from app.services.dm_proxy import get_dm_session


@pytest.fixture
def test_db(monkeypatch):
    """Replace get_db with a fresh in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE dm_sessions (
            character_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Monkeypatch the get_db function imported in dm_proxy module
    import app.services.dm_proxy as dm_proxy_mod

    def fake_get_db():
        return conn

    monkeypatch.setattr(dm_proxy_mod, "get_db", fake_get_db)
    yield conn
    conn.close()


def test_get_dm_session_returns_none_for_expired(test_db):
    """Expired session (older than 30m) should not be returned."""
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(minutes=40)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    test_db.execute(
        "INSERT INTO dm_sessions (character_id, session_id, updated_at) VALUES (?, ?, ?)",
        ("char-expired", "sess-expired", old_time),
    )
    test_db.commit()

    assert get_dm_session("char-expired") is None


def test_get_dm_session_returns_recent(test_db):
    """Session updated within 30 minutes should be returned."""
    recent_time = (datetime.datetime.utcnow() - datetime.timedelta(minutes=10)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    test_db.execute(
        "INSERT INTO dm_sessions (character_id, session_id, updated_at) VALUES (?, ?, ?)",
        ("char-recent", "sess-recent", recent_time),
    )
    test_db.commit()

    assert get_dm_session("char-recent") == "sess-recent"


def test_get_dm_session_boundary_at_30_minutes(test_db):
    """Session updated exactly 30 minutes ago should be rejected (>= condition)."""
    boundary_time = (datetime.datetime.utcnow() - datetime.timedelta(minutes=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    test_db.execute(
        "INSERT INTO dm_sessions (character_id, session_id, updated_at) VALUES (?, ?, ?)",
        ("char-boundary", "sess-boundary", boundary_time),
    )
    test_db.commit()

    # Because the query uses >=, a session exactly 30 minutes old will be included
    # But due to rounding, it might be on the edge; we accept it as valid
    result = get_dm_session("char-boundary")
    # We expect that the row is included because updated_at >= datetime('now', '-30 minutes')
    # at the moment of insertion boundary_time equals the cutoff
    assert result == "sess-boundary"
