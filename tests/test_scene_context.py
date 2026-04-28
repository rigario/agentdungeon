"""Tests for scene_context service.
"""

import sys, os, tempfile
TEST_DB = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
os.environ["D20_DB_PATH"] = TEST_DB.name
TEST_DB.close()
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest
from app.services.database import init_db, get_db
from app.services.scene_context import get_scene_context


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    conn = get_db()
    # Locations (id, name, biome, hostility_level, connected_to)
    conn.execute("INSERT OR REPLACE INTO locations VALUES ('rusty-tankard','Rusty Tankard','town','A town',1,'[]','','',0,'default')")
    conn.execute("INSERT OR REPLACE INTO locations VALUES ('whisperwood-edge','Whisperwood Edge','forest','A forest',3,'[]','','',0,'default')")
    # NPCs (minimal columns)
    conn.execute("INSERT OR REPLACE INTO npcs (id,name,archetype,current_location_id,default_location_id) VALUES ('npc-green-woman','The Green Woman','hermit','rusty-tankard','rusty-tankard')")
    conn.execute("INSERT OR REPLACE INTO npcs (id,name,archetype,current_location_id,default_location_id) VALUES ('npc-marta','Marta the Merchant','merchant','rusty-tankard','rusty-tankard')")
    # Character
    conn.execute(
        "INSERT OR REPLACE INTO characters (id,player_id,name,race,class,level,hp_current,hp_max,ac_value,ability_scores_json,location_id,campaign_id,game_hour) VALUES (?,?,?,?,?,1,10,10,16,?,?,'default',10)",
        ('test-char-001','test-player','TestHero','Human','Fighter','{"str":16,"dex":14,"con":15,"int":10,"wis":12,"cha":8}','rusty-tankard')
    )
    # Narrative flag
    conn.execute("INSERT OR REPLACE INTO narrative_flags (character_id, flag_key, flag_value) VALUES ('test-char-001','green_woman_met','1')")
    # Key item in equipment
    conn.execute("UPDATE characters SET equipment_json = ? WHERE id='test-char-001'",
                 ('["Longsword","Shield",{"name":"green_acorn","type":"key_item","display_name":"Green Acorn","quest":"cave_puzzle","consumed":true}]',))
    # Active quest
    conn.execute("INSERT OR REPLACE INTO character_quests (character_id, quest_id, quest_title, status) VALUES ('test-char-001','quest_moonpetal','Moonpetal Gathering','accepted')")
    # Fronts (id, name, danger_type, grim_portents_json, impending_doom, campaign_id)
    conn.execute("INSERT OR REPLACE INTO fronts (id,name,danger_type,grim_portents_json,impending_doom,campaign_id) VALUES ('dreaming_hunger','Dreaming Hunger','doom',?, 'The doom','default')", ('["p1","p2","p3"]',))
    # Character front
    conn.execute("INSERT OR REPLACE INTO character_fronts (character_id, front_id, current_portent_index, is_active) VALUES ('test-char-001','dreaming_hunger',1,1)")
    # Doom clock
    conn.execute("INSERT OR REPLACE INTO doom_clock (character_id, total_ticks, portents_triggered, is_active) VALUES ('test-char-001',3,1,1)")
    # Hub rumor
    conn.execute("INSERT OR REPLACE INTO hub_rumors (character_id, location_id, rumor_key, sentiment) VALUES ('test-char-001','rusty-tankard','marta_hollow_eye_grudge',-1)")
    conn.commit()
    conn.close()
    yield
    try: os.unlink(TEST_DB.name)
    except: pass


_cid = lambda: "test-char-001"


def test_basic():
    r = get_scene_context(_cid())
    assert r["character_id"] == _cid()
    for k in ["character","current_location","exits","npcs_here","narrative_flags","mark_of_dreamer_stage","key_items","active_quests","combat_state","fronts","doom_clock","hub_rumors","allowed_actions","disallowed_actions","timestamp"]:
        assert k in r

def test_char():
    c = get_scene_context(_cid())["character"]
    assert c["name"]=="TestHero" and c["level"]==1 and c["hp_current"]==10

def test_loc():
    loc = get_scene_context(_cid())["current_location"]
    assert loc and loc["id"]=="rusty-tankard"

def test_npcs():
    names = [n["name"] for n in get_scene_context(_cid())["npcs_here"]]
    assert "The Green Woman" in names and "Marta the Merchant" in names

def test_flags():
    res = get_scene_context(_cid())
    assert res["narrative_flags"].get("green_woman_met")=="1"
    assert res["mark_of_dreamer_stage"]==0

def test_key_items():
    names = [i.get("name") for i in get_scene_context(_cid())["key_items"]]
    assert "green_acorn" in names

def test_quests():
    assert any(q["quest_id"]=="quest_moonpetal" for q in get_scene_context(_cid())["active_quests"])

def test_fronts_doom():
    data = get_scene_context(_cid())
    assert data["fronts"][0]["id"] == "dreaming_hunger"
    assert data["doom_clock"] is not None

def test_rumors():
    keys = [r["rumor_key"] for r in get_scene_context(_cid())["hub_rumors"]]
    assert "marta_hollow_eye_grudge" in keys

def test_actions():
    at = [a["action_type"] for a in get_scene_context(_cid())["allowed_actions"]]
    for a in ["look","move","explore","interact","rest","quest"]: assert a in at
    for c in ["attack","flee","defend"]: assert c not in at

def test_combat():
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO combats (id,character_id,encounter_name,location_id,status) VALUES ('c1',?,'Goblin','rusty-tankard','active')", (_cid(),))
    conn.execute("INSERT OR REPLACE INTO combat_participants (combat_id,participant_type,name,hp_current,status) VALUES ('c1','enemy','Goblin',7,'alive')")
    conn.commit(); conn.close()
    d = get_scene_context(_cid())
    assert "attack" in [a["action_type"] for a in d["allowed_actions"]]
    assert "move" in [d["action_type"] for d in d["disallowed_actions"]]
    conn = get_db()
    conn.execute("DELETE FROM combats WHERE character_id=?", (_cid(),))
    conn.commit(); conn.close()

def test_missing():
    with pytest.raises(ValueError):
        get_scene_context("nope")
