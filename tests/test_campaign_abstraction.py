"""Tests for campaign/world scoping (Task 337cd54b).

Validates:
- Campaigns table exists and seeds default
- World-content tables (locations, encounters, npcs, fronts) require campaign_id
- New rows default to 'default' campaign
- Fixture creation: campaign-scoped content
- Query filtering works correctly
"""

import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import init_db, get_db
from app.services.campaigns import (
    get_campaign, get_character_campaign,
    get_campaign_locations, get_campaign_encounters, get_campaign_npcs
)


DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'test_campaigns.db')
os.environ['D20_DB_PATH'] = DB_PATH


@pytest.fixture(scope='module')
def db():
    # Use dedicated test DB so we don't clobber live dev DB
    init_db()
    conn = get_db()
    yield conn
    conn.close()


def test_campaigns_table_exists(db):
    cur = db.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"campaigns\"')
    assert cur.fetchone() is not None, "campaigns table missing"


def test_default_campaign_seeded(db):
    row = db.execute('SELECT name FROM campaigns WHERE id = \"default\"').fetchone()
    assert row is not None
    assert row[0] == 'Thornhold Whisperwood'


def test_locations_have_campaign_id(db):
    cur = db.execute('SELECT id, campaign_id FROM locations LIMIT 5')
    rows = cur.fetchall()
    assert all(r[1] == 'default' for r in rows), "locations missing correct campaign_id"


def test_encounters_have_campaign_id(db):
    cur = db.execute('SELECT id, campaign_id FROM encounters LIMIT 5')
    rows = cur.fetchall()
    assert all(r[1] == 'default' for r in rows), "encounters missing correct campaign_id"


def test_npcs_have_campaign_id(db):
    cur = db.execute('SELECT id, campaign_id FROM npcs LIMIT 5')
    rows = cur.fetchall()
    assert all(r[1] == 'default' for r in rows), "npcs missing correct campaign_id"


def test_fronts_have_campaign_id(db):
    cur = db.execute('SELECT id, campaign_id FROM fronts')
    rows = cur.fetchall()
    assert len(rows) >= 1
    assert all(r[1] == 'default' for r in rows), "fronts missing correct campaign_id"


def test_characters_have_campaign_id_default(db):
    cur = db.execute('SELECT id, campaign_id FROM characters LIMIT 5')
    rows = cur.fetchall()
    # Existing seeded characters should have default
    for row in rows:
        assert row[1] == 'default', f"character {row[0]} has campaign_id={row[1]}"


def test_get_campaign(db):
    camp = get_campaign('default')
    assert camp is not None
    assert camp['name'] == 'Thornhold Whisperwood'


def test_get_character_campaign(db):
    # Pick first seeded character
    cur = db.execute('SELECT id FROM characters LIMIT 1')
    char_id = cur.fetchone()[0]
    campaign_id = get_character_campaign(char_id)
    assert campaign_id == 'default'


def test_campaign_world_content_filtering():
    """Verify campaign-scoped queries return only content for specific campaign."""
    conn = get_db()
    # Default campaign should return all seeded world content
    locs = get_campaign_locations('default')
    assert len(locs) >= 8, f"Expected at least 8 locations, got {len(locs)}"
    encs = get_campaign_encounters('default')
    assert len(encs) >= 10
    npcs = get_campaign_npcs('default')
    assert len(npcs) >= 7
    # Unknown campaign should return empty
    locs_none = get_campaign_locations('does-not-exist')
    assert locs_none == []


if __name__ == '__main__':
    import pytest, sys
    sys.exit(pytest.main([__file__, '-v']))
