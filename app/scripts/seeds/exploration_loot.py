"""
Seed exploration loot items into the items table.

This script creates all item entries referenced by LOOT_TABLES in app/services/loot.py.
It is idempotent — running multiple times will not duplicate entries.

Usage:
    python -m app.scripts.seeds.exploration_loot
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.loot import LOOT_TABLES
from app.services.database import get_db
import datetime

def seed_exploration_loot_items():
    """Insert exploration loot items from LOOT_TABLES."""
    # Aggregate unique items across all biome tables
    items_to_seed = {}
    for biome, entries in LOOT_TABLES.items():
        for entry in entries:
            item_id = entry['item_id']
            if item_id not in items_to_seed:
                # Build display name from item_id (kebab-case → Title Case)
                name = entry.get('name', item_id.replace('-', ' ').title())
                items_to_seed[item_id] = {
                    'name': name,
                    'description': entry.get('description', f"A {name}."),
                    'rarity': entry.get('rarity', 'common'),
                    'item_type': entry.get('item_type', 'misc'),
                }

    inserted = 0
    skipped = 0
    with get_db() as conn:
        cur = conn.cursor()
        for item_id, data in sorted(items_to_seed.items()):
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO items
                    (id, name, description, rarity, item_type, is_key_item, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (
                    item_id,
                    data['name'],
                    data['description'],
                    data['rarity'],
                    data['item_type'],
                    datetime.datetime.utcnow().isoformat()
                ))
                if cur.rowcount > 0:
                    inserted += 1
                    print(f"  ✓ {item_id} | {data['rarity']} | {data['name']}")
                else:
                    skipped += 1
            except Exception as e:
                print(f"  ✗ {item_id}: {e}")
        conn.commit()

    print(f"\nDone: {inserted} inserted, {skipped} already present")

if __name__ == "__main__":
    seed_exploration_loot_items()
