"""HTTP client for the upstream D20 rules server."""

import httpx
from app.config import RULES_SERVER_URL

_client = httpx.AsyncClient(
    base_url=RULES_SERVER_URL,
    timeout=30.0,
    follow_redirects=True,
)


async def health() -> dict:
    """Check rules server health."""
    r = await _client.get("/health")
    r.raise_for_status()
    return r.json()


async def get_character(character_id: str) -> dict:
    """Get character sheet."""
    r = await _client.get(f"/characters/{character_id}")
    r.raise_for_status()
    return r.json()


async def create_character(payload: dict) -> dict:
    """Create a new character."""
    r = await _client.post("/characters", json=payload)
    r.raise_for_status()
    return r.json()


async def submit_action(character_id: str, payload: dict) -> dict:
    """Submit an action (move, attack, rest, explore, interact, puzzle, cast)."""
    r = await _client.post(f"/characters/{character_id}/actions", json=payload)
    r.raise_for_status()
    return r.json()


async def start_turn(character_id: str, payload: dict) -> dict:
    """Start an adventure turn."""
    r = await _client.post(f"/characters/{character_id}/turn/start", json=payload)
    r.raise_for_status()
    return r.json()


async def get_turn_result(character_id: str, turn_id: str) -> dict:
    """Get turn result by ID."""
    r = await _client.get(f"/characters/{character_id}/turn/result/{turn_id}")
    r.raise_for_status()
    return r.json()


async def get_latest_turn(character_id: str) -> dict:
    """Get latest turn result."""
    r = await _client.get(f"/characters/{character_id}/turn/latest")
    r.raise_for_status()
    return r.json()


async def start_combat(character_id: str, encounter_name: str, enemies_json: str) -> dict:
    """Start combat encounter."""
    r = await _client.post(
        f"/characters/{character_id}/combat/start",
        params={"encounter_name": encounter_name, "enemies_json": enemies_json},
    )
    r.raise_for_status()
    return r.json()


async def combat_act(character_id: str, payload: dict) -> dict:
    """Submit a combat action."""
    r = await _client.post(f"/characters/{character_id}/combat/act", json=payload)
    r.raise_for_status()
    return r.json()


async def get_combat(character_id: str) -> dict:
    """Get current combat state."""
    r = await _client.get(f"/characters/{character_id}/combat")
    r.raise_for_status()
    return r.json()


async def flee_combat(character_id: str, payload: dict) -> dict:
    """Attempt to flee combat."""
    r = await _client.post(f"/characters/{character_id}/combat/flee", json=payload)
    r.raise_for_status()
    return r.json()


async def list_characters() -> list:
    """List all characters."""
    r = await _client.get("/characters")
    r.raise_for_status()
    return r.json()


async def check_approval(character_id: str, payload: dict) -> dict:
    """Check if action needs human approval."""
    r = await _client.post(f"/characters/{character_id}/approval-check", json=payload)
    r.raise_for_status()
    return r.json()


async def get_narrative_flags(character_id: str) -> dict:
    """Get narrative flags for character."""
    r = await _client.get(f"/narrative/flags/{character_id}")
    r.raise_for_status()
    return r.json()


async def get_fronts() -> list:
    """Get active fronts."""
    r = await _client.get("/narrative/fronts")
    r.raise_for_status()
    return r.json()


async def get_world_context(character_id: str) -> dict:
    """Get world context for character (via latest turn)."""
    r = await _client.get(f"/characters/{character_id}/turn/latest")
    r.raise_for_status()
    return r.json().get("world_context", {})
