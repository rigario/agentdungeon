"""D20 Agent RPG — Database initialization and helpers.

Schema stores both flat columns for queries and full character
sheet in sheet_json.
"""

import sqlite3
import json
from app.config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        
        -- =========================================================
        -- CAMPAIGNS — Multi-world support (multi-tenant)
        -- =========================================================

        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            player_id TEXT NOT NULL,
            name TEXT NOT NULL,
            race TEXT NOT NULL,
            class TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            hp_current INTEGER NOT NULL,
            hp_max INTEGER NOT NULL,
            hp_temporary INTEGER DEFAULT 0,
            ac_value INTEGER NOT NULL,
            ac_description TEXT DEFAULT 'Unarmored',
            ability_scores_json TEXT NOT NULL,
            speed_json TEXT DEFAULT '{"Walk": 30}',
            skills_json TEXT DEFAULT '{}',
            saving_throws_json TEXT DEFAULT '{}',
            languages_json TEXT DEFAULT '[]',
            weapon_proficiencies_json TEXT DEFAULT '[]',
            armor_proficiencies_json TEXT DEFAULT '[]',
            equipment_json TEXT DEFAULT '[]',
            treasure_json TEXT DEFAULT '{"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0}',
            spell_slots_json TEXT DEFAULT '{}',
            spells_json TEXT DEFAULT '[]',
            feats_json TEXT DEFAULT '[]',
            conditions_json TEXT DEFAULT '{}',
            mark_of_dreamer_stage INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            location_id TEXT,
            campaign_id TEXT DEFAULT 'default',
            sheet_json TEXT,
            sheet_signature TEXT,
            approval_config TEXT DEFAULT '{}',
            aggression_slider INTEGER DEFAULT 50,
            user_id TEXT,
            agent_id TEXT,
            agent_permission_level TEXT DEFAULT 'none',
            is_archived INTEGER DEFAULT 0,
            archived_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS campaign_fronts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_portent_index INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            biome TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            hostility_level INTEGER DEFAULT 3,
            encounter_threshold INTEGER DEFAULT 10,
            recommended_level INTEGER DEFAULT 1,
            connected_to TEXT DEFAULT '[]',
            campaign_id TEXT NOT NULL DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS encounters (
            id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL,
            name TEXT NOT NULL,
            enemies_json TEXT NOT NULL,
            min_level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 20,
            loot_json TEXT DEFAULT '[]',
            description TEXT,
            image_url TEXT,
            is_opening_encounter INTEGER DEFAULT 0,
            mark_mechanic TEXT,
            wis_save_dc INTEGER,
            save_failure_effect TEXT,
            save_success_effect TEXT,
            campaign_id TEXT NOT NULL DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (location_id) REFERENCES locations(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            archetype TEXT NOT NULL,
            biome TEXT NOT NULL,
            personality TEXT,
            dialogue_templates TEXT DEFAULT '[]',
            trades_json TEXT DEFAULT '[]',
            quests_json TEXT DEFAULT '[]',
            is_quest_giver INTEGER DEFAULT 0,
            is_spirit INTEGER DEFAULT 0,
            is_enemy INTEGER DEFAULT 0,
            notes TEXT,
            image_url TEXT,
            current_location_id TEXT REFERENCES locations(id),
            default_location_id TEXT REFERENCES locations(id),
            movement_rules_json TEXT DEFAULT '{}',
            campaign_id TEXT NOT NULL DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            location_id TEXT,
            description TEXT,
            data_json TEXT DEFAULT '{}',
            approval_triggered BOOLEAN DEFAULT 0,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        -- Active combat state — one per character at a time
        CREATE TABLE IF NOT EXISTS combats (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL UNIQUE,
            encounter_name TEXT NOT NULL,
            location_id TEXT NOT NULL,
            round INTEGER DEFAULT 1,
            turn_index INTEGER DEFAULT 0,
            turn_order_json TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        -- All participants in a combat (character + enemies)
        CREATE TABLE IF NOT EXISTS combat_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            combat_id TEXT NOT NULL,
            participant_type TEXT NOT NULL,
            name TEXT NOT NULL,
            hp_current INTEGER NOT NULL,
            hp_max INTEGER NOT NULL,
            ac INTEGER NOT NULL,
            attack_bonus INTEGER DEFAULT 0,
            damage_dice TEXT DEFAULT '1d6',
            initiative INTEGER DEFAULT 0,
            initiative_mod INTEGER DEFAULT 0,
            status TEXT DEFAULT 'alive',
            is_player BOOLEAN DEFAULT 0,
            FOREIGN KEY (combat_id) REFERENCES combats(id)
        );

        -- Adventure turn results (for async agent pulls)
        CREATE TABLE IF NOT EXISTS turn_results (
            turn_id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL,
            intent_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        CREATE TABLE IF NOT EXISTS fronts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            danger_type TEXT NOT NULL,
            grim_portents_json TEXT NOT NULL,
            current_portent_index INTEGER DEFAULT 0,
            impending_doom TEXT NOT NULL,
            stakes_json TEXT DEFAULT '[]',
            is_active BOOLEAN DEFAULT 1,
            advanced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            campaign_id TEXT NOT NULL DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS narrative_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            flag_key TEXT NOT NULL,
            flag_value TEXT NOT NULL DEFAULT '1',
            source TEXT,
            set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(character_id, flag_key),
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        -- Per-character front state (multi-tenancy: each character tracks
        -- their own portent progression independently)
        CREATE TABLE IF NOT EXISTS character_fronts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            front_id TEXT NOT NULL,
            current_portent_index INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            advanced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(character_id, front_id),
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (front_id) REFERENCES fronts(id)
        );

        -- Per-character encounter history (multi-tenancy: track which
        -- encounters each character has completed)
        CREATE TABLE IF NOT EXISTS character_encounter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            encounter_id TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            was_victory BOOLEAN DEFAULT 1,
            UNIQUE(character_id, encounter_id),
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (encounter_id) REFERENCES encounters(id)
        );

        -- Items catalog (key items, loot, equipment)
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            lore_text TEXT,
            is_key_item BOOLEAN DEFAULT 0,
            image_url TEXT,
            item_type TEXT DEFAULT 'misc',
            rarity TEXT DEFAULT 'common',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Per-character inventory (many-to-many)
        CREATE TABLE IF NOT EXISTS character_items (
            character_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            is_equipped BOOLEAN DEFAULT 0,
            acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (item_id) REFERENCES items(id),
            PRIMARY KEY (character_id, item_id)
        );

        -- =========================================================
        -- AUTH SCHEMA (Hackathon Sprint — Phase 1)
        -- =========================================================

        -- Users: social login via OAuth (Gmail, X)
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            display_name TEXT,
            oauth_provider TEXT NOT NULL,  -- 'google' | 'twitter'
            oauth_provider_id TEXT NOT NULL,  -- provider user ID
            oauth_access_token TEXT,  -- latest token (encrypted in production)
            oauth_refresh_token TEXT,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP,
            UNIQUE(oauth_provider, oauth_provider_id)
        );

        -- Agents: registered by users, own Ed25519 key pairs
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            public_key TEXT NOT NULL,  -- Ed25519 public key (base64)
            public_key_fingerprint TEXT NOT NULL UNIQUE,  -- SHA-256 of public key
            private_key_encrypted TEXT,  -- encrypted private key (one-time display)
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- User sessions (Bearer tokens)
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

        -- Agent sessions (challenge-response)
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            challenge TEXT NOT NULL,
            signature TEXT,  -- agent's signed challenge
            is_verified BOOLEAN DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        -- Agent recovery log (social recovery audit trail)
        CREATE TABLE IF NOT EXISTS agent_recovery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            oauth_provider TEXT NOT NULL,
            oauth_provider_id TEXT NOT NULL,
            old_public_key_fingerprint TEXT,
            new_public_key_fingerprint TEXT,
            recovery_token TEXT,
            status TEXT DEFAULT 'completed',  -- 'initiated' | 'completed' | 'failed'
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- Character ownership columns (added here so new DBs are complete;
        -- existing DBs need the migration script in scripts/migrate_auth.py)
        -- Note: ALTER TABLE is handled by migration, not by init_db()

        -- Per-character quest tracking
        CREATE TABLE IF NOT EXISTS character_quests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            quest_id TEXT NOT NULL,
            quest_title TEXT NOT NULL,
            quest_description TEXT,
            giver_npc_id TEXT,
            giver_npc_name TEXT,
            status TEXT DEFAULT 'accepted',  -- 'accepted' | 'completed' | 'failed'
            reward_xp INTEGER DEFAULT 0,
            reward_gold INTEGER DEFAULT 0,
            reward_item TEXT,
            accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id),
            UNIQUE(character_id, quest_id)
        );

        -- =========================================================
        -- SOCIAL & EXPLORATION DEPTH — per-NPC affinity + milestones
        -- =========================================================

        -- Track per-NPC interaction history and affinity score
        CREATE TABLE IF NOT EXISTS character_npc_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            npc_id TEXT NOT NULL,
            interaction_count INTEGER DEFAULT 0,
            affinity INTEGER DEFAULT 50,  -- 0-100 scale
            first_interaction_at TEXT,
            last_interaction_at TEXT,
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (npc_id) REFERENCES npcs(id),
            UNIQUE(character_id, npc_id)
        );

        -- Track milestone rewards claimed by character
        CREATE TABLE IF NOT EXISTS character_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            milestone_type TEXT NOT NULL,  -- 'npc_count', 'exploration', 'affinity'
            threshold INTEGER NOT NULL,
            claimed_at TEXT NOT NULL,
            reward_type TEXT NOT NULL,     -- 'item', 'hint', 'flag'
            reward_data TEXT,              -- JSON: item_id, hint_text, etc.
            FOREIGN KEY (character_id) REFERENCES characters(id),
            UNIQUE(character_id, milestone_type, threshold)
        );

        -- =========================================================
        -- HUB RUMORS — Cross-NPC social state (fbe3830a)
        -- =========================================================
        CREATE TABLE IF NOT EXISTS hub_rumors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            rumor_key TEXT NOT NULL,
            sentiment INTEGER NOT NULL,          -- -1=negative, 0=neutral, 1=positive
            source_npc_id TEXT,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            spread_count INTEGER DEFAULT 1,
            UNIQUE(character_id, location_id, rumor_key),
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (location_id) REFERENCES locations(id),
            FOREIGN KEY (source_npc_id) REFERENCES npcs(id)
        );

        -- Track exploration loot finds (prevents duplicate unique items)
        CREATE TABLE IF NOT EXISTS exploration_loot_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            found_at TEXT NOT NULL,
            FOREIGN KEY (character_id) REFERENCES characters(id),
            FOREIGN KEY (item_id) REFERENCES items(id),
            UNIQUE(character_id, item_id)
        );

        -- =========================================================
        -- PLAYTEST CADENCE (accelerated tick mode)
        -- =========================================================

        -- Global playtest configuration (single row, id=1)
        CREATE TABLE IF NOT EXISTS playtest_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            cadence_mode TEXT DEFAULT 'normal',  -- 'normal' | 'playtest'
            tick_interval_seconds INTEGER DEFAULT 180,
            doom_ticks_per_portent INTEGER DEFAULT 3,
            is_active INTEGER DEFAULT 0,
            total_ticks INTEGER DEFAULT 0,
            last_tick_at TIMESTAMP,
            started_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Per-character doom clock (tick counter for playtest cadence)
        CREATE TABLE IF NOT EXISTS doom_clock (
            character_id TEXT PRIMARY KEY,
            total_ticks INTEGER DEFAULT 0,
            portents_triggered INTEGER DEFAULT 0,
            last_tick_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        -- =========================================================
        -- PLAYER PORTAL — Share tokens for public character views
        -- =========================================================

        -- Share tokens: allow unauthenticated viewing of character state
        CREATE TABLE IF NOT EXISTS share_tokens (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            label TEXT,  -- optional human label (e.g., "Playtest #1")
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,  -- NULL = never expires
            revoked INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            last_viewed_at TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        CREATE INDEX IF NOT EXISTS idx_share_tokens_character ON share_tokens(character_id);
        CREATE INDEX IF NOT EXISTS idx_share_tokens_token ON share_tokens(token);
    """)
    # Migrations: add image_url columns to existing tables (safe for new DBs too)
    for table in ["locations", "encounters"]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN image_url TEXT")
        except Exception:
            pass  # Column already exists
    # Migration: create share_tokens table for existing DBs (safe no-op for new DBs)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS share_tokens (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            revoked INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            last_viewed_at TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_share_tokens_character ON share_tokens(character_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_share_tokens_token ON share_tokens(token)")

    # -----------------------------------------------------------------
    # Campaign scoping migration — additive, idempotent
    # -----------------------------------------------------------------
    for tbl, col in [
        ("locations", "campaign_id"),
        ("encounters", "campaign_id"),
        ("npcs", "campaign_id"),
        ("fronts", "campaign_id"),
        ("characters", "campaign_id"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} TEXT NOT NULL DEFAULT 'default'")
        except Exception:
            pass

    # Create indices (now that columns exist)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_campaign ON locations(campaign_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_encounters_campaign ON encounters(campaign_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_npcs_campaign ON npcs(campaign_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fronts_campaign ON fronts(campaign_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_campaign ON characters(campaign_id)")

    # Seed default campaign (idempotent)
    conn.execute("INSERT OR IGNORE INTO campaigns (id, name, description) VALUES ('default', 'Thornhold Whisperwood', 'Original single-world campaign — pre-migration default')")

    # =========================================================
    # DM RUNTIME — Session persistence for async recap/resume
    # =========================================================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dm_sessions (
            character_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dm_sessions_updated ON dm_sessions(updated_at)")

    conn.commit()
    conn.close()


def init_character_fronts(character_id: str, conn: sqlite3.Connection = None):
    """Initialize per-character front state from the global front templates.
    
    Multi-tenancy: Each character gets their own front progression,
    independent of other characters. Called on character creation.
    """
    should_close = conn is None
    if conn is None:
        conn = get_db()
    
    # Get all global front templates
    fronts = conn.execute("SELECT id FROM fronts").fetchall()
    for front in fronts:
        # Insert per-character front state if not exists
        conn.execute(
            """INSERT OR IGNORE INTO character_fronts 
               (character_id, front_id, current_portent_index, is_active, advanced_at)
               VALUES (?, ?, 0, 1, CURRENT_TIMESTAMP)""",
            (character_id, front["id"])
        )
    
    if should_close:
        conn.commit()
        conn.close()


def init_character_fronts_for_all():
    """Initialize character_fronts for all existing characters who don't have entries yet.
    Used for migration when adding multi-tenancy to an existing DB.
    """
    conn = get_db()
    characters = conn.execute("SELECT id FROM characters").fetchall()
    for char in characters:
        # Check if this character already has front entries
        existing = conn.execute(
            "SELECT COUNT(*) FROM character_fronts WHERE character_id = ?",
            (char["id"],)
        ).fetchone()[0]
        if existing == 0:
            init_character_fronts(char["id"], conn)
    conn.commit()
    conn.close()


def get_character_front(character_id: str, front_id: str, conn: sqlite3.Connection = None) -> dict | None:
    """Get a character's personal front state. Falls back to global front defaults."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    
    row = conn.execute(
        "SELECT * FROM character_fronts WHERE character_id = ? AND front_id = ?",
        (character_id, front_id)
    ).fetchone()
    
    if row:
        result = dict(row)
    else:
        # Fallback to global front (shouldn't happen after init, but safe)
        global_front = conn.execute(
            "SELECT * FROM fronts WHERE id = ?", (front_id,)
        ).fetchone()
        if global_front:
            result = dict(global_front)
            result["current_portent_index"] = 0
            result["is_active"] = 1
        else:
            result = None
    
    if should_close:
        conn.close()
    return result


def db_healthcheck() -> bool:
    """Check if database is accessible."""
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False
