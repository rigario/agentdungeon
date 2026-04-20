"""Migration: Add game_hour column to characters table for time-of-day tracking."""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from app.config import DB_PATH


def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Check if column already exists
    cols = conn.execute("PRAGMA table_info(characters)").fetchall()
    col_names = [c[1] for c in cols]
    
    if "game_hour" not in col_names:
        conn.execute("ALTER TABLE characters ADD COLUMN game_hour INTEGER DEFAULT 8")
        print("[OK] Added game_hour column (default 8 = morning)")
    else:
        print("[SKIP] game_hour column already exists")
    
    conn.commit()
    conn.close()
    print("[DONE] Time-of-day migration complete")


if __name__ == "__main__":
    migrate()
