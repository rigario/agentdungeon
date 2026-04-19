#!/usr/bin/env python3
"""Migration script for auth schema — Task 1.1 Auth Database Schema.

Adds auth tables (users, agents, user_sessions, agent_sessions, agent_recovery_log)
to an existing D20 database that already has the game tables.

Also adds user_id, agent_id, agent_permission_level columns to characters.

Usage:
    cd ~/Projects/rigario-d20
    python -m app.scripts.migrate_auth
"""

import sqlite3
import uuid
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.config import DB_PATH


def migrate():
    """Run the auth schema migration."""
    print(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")

    # Check which tables already exist
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    existing_tables = {row[0] for row in existing}

    auth_tables = ['users', 'agents', 'user_sessions', 'agent_sessions', 'agent_recovery_log']
    missing = [t for t in auth_tables if t not in existing_tables]

    if not missing:
        print("All auth tables already exist. Checking character columns...")
    else:
        print(f"Creating missing auth tables: {missing}")

    # Create auth tables (CREATE IF NOT EXISTS is safe)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            display_name TEXT,
            oauth_provider TEXT NOT NULL,
            oauth_provider_id TEXT NOT NULL,
            oauth_access_token TEXT,
            oauth_refresh_token TEXT,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP,
            UNIQUE(oauth_provider, oauth_provider_id)
        );

        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            public_key TEXT NOT NULL,
            public_key_fingerprint TEXT NOT NULL UNIQUE,
            private_key_encrypted TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS user_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            challenge TEXT NOT NULL,
            signature TEXT,
            is_verified BOOLEAN DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS agent_recovery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            oauth_provider TEXT NOT NULL,
            oauth_provider_id TEXT NOT NULL,
            old_public_key_fingerprint TEXT,
            new_public_key_fingerprint TEXT,
            recovery_token TEXT,
            status TEXT DEFAULT 'completed',
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    print("Auth tables created/verified.")

    # Add ownership columns to characters (if not already present)
    char_columns = conn.execute("PRAGMA table_info(characters)").fetchall()
    col_names = {c[1] for c in char_columns}

    alter_statements = []
    if 'user_id' not in col_names:
        alter_statements.append("ALTER TABLE characters ADD COLUMN user_id TEXT")
    if 'agent_id' not in col_names:
        alter_statements.append("ALTER TABLE characters ADD COLUMN agent_id TEXT")
    if 'agent_permission_level' not in col_names:
        alter_statements.append("ALTER TABLE characters ADD COLUMN agent_permission_level TEXT DEFAULT 'none'")

    for stmt in alter_statements:
        print(f"  Running: {stmt}")
        conn.execute(stmt)

    # Create indexes (if not exists)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_user_id ON characters(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_agent_id ON characters(agent_id)")

    # Backfill: assign existing characters to a default user if user_id is NULL
    default_user_id = str(uuid.uuid4())
    count = conn.execute("SELECT COUNT(*) FROM characters WHERE user_id IS NULL").fetchone()[0]
    if count > 0:
        print(f"Backfilling {count} characters with default user_id...")
        conn.execute(
            "UPDATE characters SET user_id = ? WHERE user_id IS NULL",
            (default_user_id,)
        )
        print(f"  Created default user_id: {default_user_id}")

    # Create indexes for auth tables
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_oauth ON users(oauth_provider, oauth_provider_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_fingerprint ON agents(public_key_fingerprint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_recovery_agent_id ON agent_recovery_log(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_recovery_user_id ON agent_recovery_log(user_id)")

    conn.commit()
    conn.close()

    # Verify
    verify()

    print("\n✅ Auth schema migration complete.")
    return True


def verify():
    """Verify migration succeeded."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n--- Verification ---")

    # Check auth tables exist
    auth_tables = ['users', 'agents', 'user_sessions', 'agent_sessions', 'agent_recovery_log']
    for table in auth_tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count} rows")

    # Check character columns
    cursor.execute("PRAGMA table_info(characters)")
    cols = [c[1] for c in cursor.fetchall()]
    for col in ['user_id', 'agent_id', 'agent_permission_level']:
        status = "✅" if col in cols else "❌"
        print(f"  characters.{col}: {status}")

    # Check no NULL user_ids
    cursor.execute("SELECT COUNT(*) FROM characters WHERE user_id IS NULL")
    null_count = cursor.fetchone()[0]
    print(f"  characters with NULL user_id: {null_count} {'✅' if null_count == 0 else '❌'}")

    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = [r[0] for r in cursor.fetchall()]
    print(f"  Indexes: {len(indexes)} total")

    conn.close()


if __name__ == "__main__":
    migrate()
