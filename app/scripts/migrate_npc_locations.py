"""Migration: Add NPC location tracking columns.

Adds current_location_id, default_location_id, and movement_rules_json
to the npcs table. Populates default locations based on narrative assignments.

Run once: python -m app.scripts.migrate_npc_locations
"""

import sqlite3
import json
import os

DB_PATH = os.environ.get("D20_DB_PATH", "data/d20.db")

NPC_LOCATIONS = {
    'npc-aldric': 'rusty-tankard',
    'npc-marta': 'thornhold',
    'npc-ser-maren': 'thornhold',
    'npc-sister-drenna': 'south-road',
    'npc-kira': 'crossroads',
    'npc-green-woman': 'forest-edge',
    'npc-torren': 'mountain-pass',
    'npc-brother-kol': 'cave-depths',
    'npc-del-ghost': 'rusty-tankard',
}

NPC_MOVEMENT_RULES = {
    'npc-aldric': {
        'can_visit': ['rusty-tankard', 'thornhold'],
        'schedule': 'static',
        'triggers': []
    },
    'npc-marta': {
        'can_visit': ['thornhold', 'crossroads'],
        'schedule': 'static',
        'triggers': []
    },
    'npc-ser-maren': {
        'can_visit': ['thornhold', 'south-road', 'crossroads'],
        'schedule': 'patrol',
        'triggers': [
            {'flag': 'collateral_near_town', 'target': 'south-road',
             'description': 'Maren rides out to investigate reports of danger near town'}
        ]
    },
    'npc-sister-drenna': {
        'can_visit': ['south-road', 'crossroads', 'forest-edge'],
        'schedule': 'static',
        'triggers': [
            {'quest_complete': 'quest-save-drenna-child', 'target': 'thornhold',
             'description': 'Drenna returns to Thornhold with her child, grateful for rescue'}
        ]
    },
    'npc-kira': {
        'can_visit': ['crossroads', 'south-road', 'thornhold'],
        'schedule': 'travel',
        'triggers': []
    },
    'npc-green-woman': {
        'can_visit': ['forest-edge', 'deep-forest', 'moonpetal-glade'],
        'schedule': 'progressive',
        'triggers': [
            {'flag': 'green_woman_suppression_1', 'target': 'deep-forest',
             'description': 'The Green Woman retreats deeper into Whisperwood'},
            {'flag': 'green_woman_suppression_2', 'target': 'moonpetal-glade',
             'description': 'The Green Woman has withdrawn to the Moonpetal Glade'},
            {'flag': 'green_woman_suppression_3', 'target': None,
             'description': 'The Green Woman has vanished from the forest entirely'}
        ]
    },
    'npc-torren': {
        'can_visit': ['mountain-pass', 'crossroads'],
        'schedule': 'static',
        'triggers': [
            {'flag': 'kol_backstory_known', 'target': 'cave-entrance',
             'description': 'Torren descends from the pass, now knowing Kol\'s true nature'}
        ]
    },
    'npc-brother-kol': {
        'can_visit': ['cave-depths', 'seal-chamber'],
        'schedule': 'static',
        'triggers': [
            {'flag': 'seal_keys_placed', 'target': 'seal-chamber',
             'description': 'Brother Kol moves to the Seal Chamber for the final ritual'}
        ]
    },
    'npc-del-ghost': {
        'can_visit': ['rusty-tankard'],
        'schedule': 'static',
        'triggers': []
    }
}


def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Check if columns already exist
    cols = [row['name'] for row in conn.execute("PRAGMA table_info(npcs)")]
    if 'current_location_id' in cols:
        print("Migration already applied — columns exist.")
        conn.close()
        return

    # Add columns
    conn.execute("ALTER TABLE npcs ADD COLUMN current_location_id TEXT REFERENCES locations(id)")
    conn.execute("ALTER TABLE npcs ADD COLUMN default_location_id TEXT REFERENCES locations(id)")
    conn.execute("ALTER TABLE npcs ADD COLUMN movement_rules_json TEXT DEFAULT '{}'")
    conn.commit()
    print("Added columns: current_location_id, default_location_id, movement_rules_json")

    # Populate data
    for npc_id, location_id in NPC_LOCATIONS.items():
        rules = NPC_MOVEMENT_RULES.get(npc_id, {})
        conn.execute("""
            UPDATE npcs
            SET current_location_id = ?,
                default_location_id = ?,
                movement_rules_json = ?
            WHERE id = ?
        """, (location_id, location_id, json.dumps(rules), npc_id))

    conn.commit()

    # Verify
    for row in conn.execute("SELECT id, name, current_location_id FROM npcs ORDER BY name"):
        print(f"  {row['name']}: {row['current_location_id']}")

    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
