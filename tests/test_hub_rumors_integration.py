"""
Integration test for fbe3830a — prove cross-NPC reaction across interactions.
"""
import tempfile
import sys
import os
import pytest

TEST_DB = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
os.environ["D20_DB_PATH"] = TEST_DB.name
TEST_DB.close()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.services.database import init_db, get_db
from app.services import hub_rumors


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    conn = get_db()
    # Clear any lingering state (hub_rumors, characters, npcs)
    conn.executescript("""
        DELETE FROM hub_rumors;
        DELETE FROM characters;
        DELETE FROM npcs;
        DELETE FROM locations;
    """)
    # Minimal hub locations
    conn.execute("""
        INSERT OR REPLACE INTO locations (id, name, biome, hostility_level, connected_to)
        VALUES ('thornhold','Thornhold','town',1,'[]'),
               ('rusty-tankard','Rusty Tankard','town',1,'[]')
    """)
    # NPCs in both hubs
    conn.execute("""
        INSERT OR REPLACE INTO npcs (id, name, archetype, biome, current_location_id, default_location_id)
        VALUES ('npc-marta','Marta the Merchant','merchant','town','thornhold','thornhold'),
               ('npc-ser-maren','Ser Maren','guard','town','thornhold','thornhold'),
               ('npc-aldric','Aldric the Innkeeper','innkeeper','town','rusty-tankard','rusty-tankard')
    """)
    # Character at thornhold
    conn.execute("""
        INSERT OR REPLACE INTO characters (id, player_id, name, race, class, level,
            hp_current, hp_max, ac_value, ability_scores_json, location_id)
        VALUES ('test-hero','p1','TestHero','Human','Fighter',1,10,10,16,'{}','thornhold')
    """)
    conn.commit()
    conn.close()
    yield
    try: os.unlink(TEST_DB.name)
    except: pass


def _char_id():
    return 'test-hero'


def test_marta_dialogue_spreads_to_ser_maren():
    """PROOF fbe3830a: Marta's Hollow Eye warning rumor affects Ser Maren's reaction."""
    char_id = _char_id()
    loc = 'thornhold'

    hub_rumors.record_rumor(char_id, loc, 'marta_hollow_eye_grudge', -1, 'npc-marta')

    rumors = hub_rumors.get_hub_rumors(char_id, loc)
    assert len(rumors) == 1
    assert rumors[0]['rumor_key'] == 'marta_hollow_eye_grudge'

    reaction = hub_rumors.get_reaction_modifiers(char_id, loc, 'npc-ser-maren')
    assert reaction['affinity_bonus'] == 5
    assert reaction['tone_modifier'] == 'respectful'
    assert reaction['dialogue_hint'] == 'marta_grudge_known'


def test_aldric_confession_warms_marta_and_ser_maren():
    """PROOF fbe3830a: Aldric's confession rumor affects both other NPCs."""
    char_id = _char_id()
    loc = 'thornhold'

    # Aldric confesses — recorded at 'thornhold' to test cross-reaction in same hub
    hub_rumors.record_rumor(char_id, loc, 'aldric_confessed', 1, 'npc-aldric')

    # Marta reacts warmly
    marta = hub_rumors.get_reaction_modifiers(char_id, loc, 'npc-marta')
    assert marta['affinity_bonus'] == 5
    assert marta['tone_modifier'] == 'warmer'

    # Ser Maren appreciates truth even more
    maren = hub_rumors.get_reaction_modifiers(char_id, loc, 'npc-ser-maren')
    assert maren['affinity_bonus'] == 8
    assert maren['tone_modifier'] == 'respectful'


def test_hub_social_state_concise():
    """PROOF fbe3830a: Hub social state for DM context is concise (<200 chars)."""
    char_id = _char_id()
    loc = 'thornhold'

    hub_rumors.record_rumor(char_id, loc, 'aldric_confessed', 1, 'npc-aldric')
    hub_rumors.record_rumor(char_id, loc, 'marta_hollow_eye_grudge', -1, 'npc-marta')

    state = hub_rumors.get_hub_social_state(char_id, loc)

    assert len(state['rumors']) == 2
    summary = state['summary_text']
    assert 0 < len(summary) < 200  # token-efficient for LLM context


def test_rumors_idempotent_updates_not_duplicates():
    """PROOF fbe3830a: Same rumor updates existing row, doesn't create duplicates."""
    char_id = _char_id()
    loc = 'thornhold'

    is_new1 = hub_rumors.record_rumor(char_id, loc, 'marta_hollow_eye_grudge', -1, 'npc-marta')
    assert is_new1 is True

    is_new2 = hub_rumors.record_rumor(char_id, loc, 'marta_hollow_eye_grudge', -1, 'npc-marta')
    assert is_new2 is False

    rumors = hub_rumors.get_hub_rumors(char_id, loc)
    assert rumors[0]['spread_count'] == 2
