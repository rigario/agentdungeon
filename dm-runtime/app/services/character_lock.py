"""Per-character distributed lock for DM runtime turns.

Serializes access to a single character across DM workers so concurrent turns do
not corrupt state or session continuity.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Optional

import redis.asyncio as redis

REDIS_URL = os.environ.get("DM_REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LOCK_TTL_MS = 30_000
_LOCK_PREFIX = "d20:dm_lock"
_client: redis.Redis | None = None


async def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return _client


def _key(character_id: str) -> str:
    return f"{_LOCK_PREFIX}:{character_id}"


async def acquire_character_lock(
    character_id: str,
    timeout: int = 25,
    block: bool = True,
    block_timeout: float | None = None,
) -> Optional[str]:
    client = await _redis()
    token = str(uuid.uuid4())
    key = _key(character_id)
    if not block:
        acquired = await client.set(key, token, nx=True, px=LOCK_TTL_MS)
        return token if acquired else None

    deadline = time.monotonic() + (block_timeout if block_timeout is not None else max(0.0, timeout - 5))
    while time.monotonic() < deadline:
        acquired = await client.set(key, token, nx=True, px=LOCK_TTL_MS)
        if acquired:
            return token
        await asyncio.sleep(0.1)
    return None


async def release_character_lock(character_id: str, lock_token: str) -> bool:
    if not lock_token:
        return False
    client = await _redis()
    key = _key(character_id)
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """
    try:
        result = await client.eval(script, 1, key, lock_token)
        return bool(result)
    except Exception:
        return False
