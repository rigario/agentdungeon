"""Migration: Add archive columns to characters table for recoverable deletion.

Adds is_archived (INTEGER DEFAULT 0) and archived_at (TIMESTAMP) columns.
Safe to run multiple times — uses IF NOT EXISTS patterns.
"""

import sqlite3
from app.config import DB_PATH


def migrate():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")

    # Check existing columns
    char_columns = conn.execute("PRAGMA table_info(characters)").fetchall()
    col_names = {c[1] for c in char_columns}

    alter_statements = []
    if 'is_archived' not in col_names:
        alter_statements.append(
            "ALTER TABLE characters ADD COLUMN is_archived INTEGER DEFAULT 0"
        )
    if 'archived_at' not in col_names:
        alter_statements.append(
            "ALTER TABLE characters ADD COLUMN archived_at TIMESTAMP"
        )

    for stmt in alter_statements:
        print(f"  Running: {stmt}")
        conn.execute(stmt)

    if alter_statements:
        conn.commit()
        print(f"Archive migration complete: {len(alter_statements)} columns added.")
    else:
        print("Archive columns already present — no changes needed.")

    conn.close()


if __name__ == "__main__":
    migrate()
