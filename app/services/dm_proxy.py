"""DM Proxy Client — Calls the d20-dm-runtime service for narration.

This module implements the connection between the rules-server and the
DM runtime (Hermes agent). The rules-server retains authority for all
rule validation, state mutation, and DB writes. The DM runtime ONLY
produces narrated prose and player-facing choices.

Flow:
  1. Rules-server compiles world_context via build_world_context()
  2. Rules-server resolves mechanics locally (single source of truth)
  3. Rules-server POST /dm/narrate to d20-dm-runtime with resolved_result + context
  4. DM runtime narrates only; it does not re-enter rules action routing
  5. Rules-server merges DM narration into the action response
  6. Rules-server saves new dm_session_id for continuity

Env:
  DM_PROXY_URL   default "http://d20-dm-runtime:8610"
  DM_TIMEOUT     default 30.0
"""

from __future__ import annotations
import os
import json
import logging
from typing import Optional, Dict, Any

import httpx

from app.services.database import get_db
from app.services.key_items import KEY_ITEMS
from app.services import affinity
from app.services import hub_rumors

logger = logging.getLogger(__name__)

DM_PROXY_URL = os.environ.get("DM_PROXY_URL", "http://d20-dm-runtime:8610")
DM_TIMEOUT = float(os.environ.get("DM_TIMEOUT", "65.0"))

_shared_client: Optional[httpx.AsyncClient] = None


def set_http_client(client: httpx.AsyncClient) -> None:
    global _shared_client
    _shared_client = client


def get_dm_session(character_id: str) -> Optional[str]:
    conn = get_db()
    row = conn.execute(
        "SELECT session_id FROM dm_sessions "
        "WHERE character_id = ? AND updated_at >= datetime('now', '-30 minutes')",
        (character_id,)
    ).fetchone()
    conn.close()
    return row["session_id"] if row else None


def save_dm_session(character_id: str, session_id: str) -> None:
    conn = get_db()
    conn.execute(
        """
        INSERT INTO dm_sessions (character_id, session_id, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(character_id) DO UPDATE SET
            session_id = excluded.session_id,
            updated_at = excluded.updated_at
        """,
        (character_id, session_id)
    )
    conn.commit()
    conn.close()
    logger.info(f"Saved DM session for {character_id}: {session_id[:12]}...")


async def build_world_context(character_id: str) -> Dict[str, Any]:
    """Compile pre-action ServerWorldContext for character."""
    conn = get_db()

    char_row = conn.execute(
        "SELECT * FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not char_row:
        raise ValueError(f"Character not found: {character_id}")
    char = dict(char_row)

    loc_row = conn.execute(
        "SELECT * FROM locations WHERE id = ?", (char["location_id"],)
    ).fetchone()
    location = dict(loc_row) if loc_row else {}

    npc_rows = conn.execute(
        "SELECT * FROM npcs WHERE current_location_id = ?",
        (char["location_id"],)
    ).fetchall()
    npcs = [dict(r) for r in npc_rows]

    connections = json.loads(location.get("connected_to", "[]") or "[]")

    encounter_rows = conn.execute(
        "SELECT * FROM encounters WHERE location_id = ?",
        (char["location_id"],)
    ).fetchall()
    encounters = []
    for row in encounter_rows:
        enc = dict(row)
        try:
            enc["enemies"] = json.loads(enc.get("enemies_json", "[]") or "[]")
        except Exception:
            enc["enemies"] = []
        encounters.append(enc)

    from app.services.atmosphere import get_atmospheric_description
    
    # First: load front progression (needed for portent_index)
    front_rows = conn.execute(
        """
        SELECT f.id, f.name, f.danger_type, f.grim_portents_json, cf.current_portent_index
        FROM fronts f
        JOIN character_fronts cf ON cf.front_id = f.id
        WHERE cf.character_id = ? AND cf.is_active = 1
        """,
        (character_id,)
    ).fetchall()
    front_progression = [
        {
            "id": r["id"],
            "name": r["name"],
            "danger_type": r["danger_type"],
            "current_portent": r["current_portent_index"],
            "grim_portents": json.loads(r["grim_portents_json"] or "[]"),
        }
        for r in front_rows
    ]

    # Now compute portent_index from loaded front_progression
    mark_stage = char.get("mark_of_dreamer_stage", 0)
    portent_index = 0
    for front in front_progression:
        if front.get("id") == "dreaming_hunger":
            portent_index = front.get("current_portent", 0)
            break
    game_hour = char.get("game_hour", 8)
    biome = location.get("biome")
    atmosphere = {
        "mark_stage": mark_stage,
        "overlay": get_atmospheric_description(location["id"], mark_stage, portent_index, game_hour=game_hour, biome=biome),
    }

    quest_rows = conn.execute(
        "SELECT quest_id, quest_title, quest_description, giver_npc_name, status "
        "FROM character_quests WHERE character_id = ? "
        "AND status IN ('active','accepted')",
        (character_id,)
    ).fetchall()
    active_quests = [
        {
            "quest_id": r["quest_id"],
            "title": r["quest_title"],
            "description": r["quest_description"],
            "giver": r["giver_npc_name"],
            "status": r["status"],
        }
        for r in quest_rows
    ]

    # -------------------------------------------------------------------------
    # Key Item Extraction — derive from equipment_json (not character_items)
    # -------------------------------------------------------------------------
    # Key items are stored as structured objects in character.equipment_json.
    # They are not tracked in character_items junction table.
    # Enrich each key item from the global KEY_ITEMS definitions.
    equipment = json.loads(char.get("equipment_json", "[]") or "[]")
    key_items = []
    for item in equipment:
        if isinstance(item, dict) and item.get("type") == "key_item":
            ki_name = item.get("name")
            ki_def = KEY_ITEMS.get(ki_name, {})
            key_items.append({
                "id": ki_name,
                "name": ki_def.get("display_name", ki_name),
                "description": ki_def.get("description", item.get("description", "")),
                "lore": ki_def.get("deeper_lore", ""),
                "quantity": 1,
            })
    # -------------------------------------------------------------------------

    # Social Context — affinity, milestones, exploration loot log
    # -------------------------------------------------------------------------
    # Fetch per-NPC affinity for relationship-status narration
    all_affinities = affinity.get_all_affinities(character_id)
    # Filter to only NPCs with recorded affinity
    social_affinities = {npc_id: score for npc_id, score in all_affinities.items() if score is not None}
    
    # Character milestone history (recent achievements/completed goals)
    milestone_rows = conn.execute(
        "SELECT milestone_type, threshold, claimed_at, reward_type, reward_data "
        "FROM character_milestones WHERE character_id = ? "
        "ORDER BY claimed_at DESC LIMIT 10",
        (character_id,)
    ).fetchall()
    milestones = [
        {
            "type": r["milestone_type"],
            "threshold": r["threshold"],
            "claimed_at": r["claimed_at"],
            "reward_type": r["reward_type"],
            "reward_data": json.loads(r["reward_data"] or "{}"),
        }
        for r in milestone_rows
    ]
    
    # Exploration loot log — track unique items found during searches
    loot_rows = conn.execute(
        "SELECT ell.location_id, ell.item_id, ell.found_at, i.name, i.description, i.rarity "
        "FROM exploration_loot_log ell "
        "JOIN items i ON i.id = ell.item_id "
        "WHERE ell.character_id = ? "
        "ORDER BY ell.found_at DESC LIMIT 10",
        (character_id,)
    ).fetchall()
    loot_history = [
        {
            "location_id": r["location_id"],
            "item_id": r["item_id"],
            "item_name": r["name"],
            "item_description": r["description"],
            "rarity": r["rarity"],
            "found_at": r["found_at"],
        }
        for r in loot_rows
    ]
    
    # -------------------------------------------------------------------------

    conn.close()

    compact_char = {
        "id": char["id"],
        "name": char["name"],
        "race": char["race"],
        "class_": char["class"],
        "level": char["level"],
        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
        "location_id": char["location_id"],
        "mark_of_dreamer_stage": char.get("mark_of_dreamer_stage", 0),
    }

    return {
        "location": location,
        "character": compact_char,
        "npcs": npcs,
        "connections": connections,
        "encounters": encounters,
        "atmosphere": atmosphere,
        "front_progression": front_progression,
        "active_quests": active_quests,
        "key_items": key_items,
        "social_context": {
            "affinities": social_affinities,
            "milestones": milestones,
            "loot_history": loot_history,
            "hub_social": hub_rumors.get_hub_social_state(character_id, location['id']),
        },
    }


class DMProxyClient:
    """Async HTTP client for DM runtime /dm/turn endpoint."""

    def __init__(
        self,
        base_url: str = None,
        timeout: float = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = (base_url or DM_PROXY_URL).rstrip("/")
        self.timeout = timeout or DM_TIMEOUT
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if _shared_client is not None:
            return _shared_client
        return httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def turn(
        self,
        character_id: str,
        world_context: Dict[str, Any],
        player_message: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        payload = {
            "character_id": character_id,
            "world_context": world_context,
            "message": player_message,
        }
        if session_id:
            payload["session_id"] = session_id

        url = f"{self.base_url}/dm/turn"
        logger.info(f"DM proxy → {url} (char={character_id}, sess={session_id or 'new'})")

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            new_sid = data.get("session_id")
            if new_sid and new_sid != session_id:
                await save_dm_session(character_id, new_sid)
            elif session_id:
                # Refresh session activity timestamp on every successful turn
                await save_dm_session(character_id, session_id)

            return data
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response else ""
            logger.error(f"DM proxy HTTP {e.response.status_code}: {body}")
            raise
        except Exception as e:
            logger.error(f"DM proxy error: {e}")
            raise

    async def narrate(
        self,
        character_id: str,
        world_context: Dict[str, Any],
        resolved_result: Dict[str, Any],
        player_message: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Narrate an already-resolved rules result without re-entering /dm/turn.

        This endpoint is safe to call from rules-server action handlers because it
        does not ask the DM runtime to route or execute another rules action.
        """
        client = await self._get_client()
        payload = {
            "character_id": character_id,
            "world_context": world_context,
            "resolved_result": resolved_result,
            "player_message": player_message,
        }
        if session_id:
            payload["session_id"] = session_id

        url = f"{self.base_url}/dm/narrate"
        logger.info(f"DM proxy narrate → {url} (char={character_id}, sess={session_id or 'new'})")

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            new_sid = data.get("session_id")
            if new_sid and new_sid != session_id:
                save_dm_session(character_id, new_sid)
            elif session_id:
                save_dm_session(character_id, session_id)

            return data
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response else ""
            logger.error(f"DM proxy narrate HTTP {e.response.status_code}: {body}")
            raise
        except Exception as e:
            logger.error(f"DM proxy narrate error: {e}")
            raise


_proxy: Optional[DMProxyClient] = None


def get_dm_proxy() -> DMProxyClient:
    global _proxy
    if _proxy is None:
        _proxy = DMProxyClient()
    return _proxy
