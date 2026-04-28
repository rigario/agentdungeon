from pathlib import Path
import pytest
import sqlite3
from app.services import hub_rumors

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open(str(Path(__file__).resolve().parents[1] / "app/services/database_schema.sql")) as f:
        conn.executescript(f.read())
    conn.execute("INSERT INTO locations (id,name,biome,hostility_level,connected_to) VALUES ('t','T','town',1,'[]')")
    print("\n[FIXTURE] db_conn created, closed:", conn.is_closed)
    yield conn
    conn.close()
    print("[FIXTURE] db_conn closed")

def test_one(db_conn, monkeypatch):
    print("[TEST] db_conn closed?", db_conn.is_closed)
    monkeypatch.setattr(hub_rumors, "get_db", lambda: db_conn)
    print("[TEST] patched, calling record_rumor...")
    hub_rumors.record_rumor("c", "t", "test", 1, "npc-x")
    print("[TEST] record_rumor succeeded")
