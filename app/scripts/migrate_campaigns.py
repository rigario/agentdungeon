"""D20 Agent RPG — Campaign Multi-Tenancy Migration.

Adds campaign_id column to world content tables and initializes
a default campaign. This is an additive, backward-compatible change.
Run once: python -m app.scripts.migrate_campaigns
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.services.database import get_db


def migrate():
    conn = get_db()
    cursor = conn.cursor()

    migrated = []

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO campaigns (id, name, description)
        VALUES ('default', 'Thornhold Whisperwood',
                'Original world — pre-migration default')
    """)

    for table in ['locations', 'encounters', 'npcs', 'fronts', 'characters']:
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor.fetchall()]
            if 'campaign_id' not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN campaign_id TEXT DEFAULT 'default'")
                migrated.append(f"{table}: added campaign_id column (new)")
            count = cursor.execute(
                f"UPDATE {table} SET campaign_id = 'default' WHERE campaign_id IS NULL OR campaign_id = ''"
            ).rowcount
            if count > 0:
                migrated.append(f"{table}: backfilled {count} row(s)")
        except Exception as e:
            print(f"[WARN] Could not backfill {table}: {e}")

    conn.commit()
    conn.close()

    print("[Campaign Migration] Complete")
    for msg in migrated:
        print(f"  • {msg}")


if __name__ == "__main__":
    migrate()
