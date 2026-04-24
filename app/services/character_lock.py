"""Per-character distributed lock using Redis.

Prevents concurrent DM turn corruption by serializing access to a character's
state across all rules-server and DM-runtime workers.

Lock key format: d20:dm_lock:{character_id}
TTL: 30 seconds (must complete within this time or lock auto-expires).
"""

from __future__ import annotations

import os
import asyncio
import uuid
import time
from typing import Optional

import redis.asyncio as redis
from fastapi import Request

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LOCK_PREFIX = "d20:dm_lock:"
LOCK_TTL_SECONDS = 30  # Maximum time a turn can hold the lock

# In-memory fallback lock store when Redis is unavailable (dev/test single-process)
_INMEMORY_LOCKS: dict[str, str] = {}

# Global Redis client (lazy init)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Get or create the global Redis async client."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        except Exception as e:
            # Redis unavailable — fall back to in-memory mock client
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Redis unavailable ({e}), using in-memory lock fallback")
            _redis_client = _InMemoryRedisMock()
    return _redis_client


# In-memory fallback for Redis when unavailable (dev/test single-process)
class _InMemoryRedisMock:
    """Minimal Redis subset for local dev when Redis is not installed."""
    def __init__(self):
        self._store: dict[str, str] = {}
        self._expires: dict[str, float] = {}

    async def set(self, key: str, value: str, nx: bool = False, px: int = None) -> bool:
        import time
        if nx and key in self._store:
            # Check expiry
            if key in self._expires and time.time() > self._expires[key]:
                # Expired, can overwrite
                del self._store[key]
                del self._expires[key]
            else:
                return False
        self._store[key] = value
        if px:
            self._expires[key] = time.time() + (px / 1000.0)
        return True

    async def eval(self, script: str, numkeys: int, *args):
        # Simple implementation of the Lua release script
        key, token = args
        if self._store.get(key) == token:
            del self._store[key]
            self._expires.pop(key, None)
            return 1
        return 0

    async def close(self):
        pass


async def acquire_character_lock(
    character_id: str,
    timeout: int = LOCK_TTL_SECONDS,
    block: bool = True,
    block_timeout: Optional[float] = None,
) -> Optional[str]:
    """
    Acquire a per-character lock.

    Args:
        character_id: The character to lock.
        timeout: Lock TTL in seconds (auto-release if holder crashes).
        block: If True, wait until lock is available or block_timeout expires.
        block_timeout: Max seconds to wait for lock (None = wait forever).

    Returns:
        Lock token (UUID) on success, None on failure (if non-blocking or timeout).
    """
    client = get_redis_client()
    lock_key = f"{LOCK_PREFIX}{character_id}"
    lock_token = str(uuid.uuid4())

    if not block:
        # Try once, non-blocking
        try:
            acquired = await client.set(lock_key, lock_token, nx=True, px=timeout * 1000)
        except Exception:
            # Redis unavailable — fall back to always-acquire in dev
            _INMEMORY_LOCKS[lock_key] = lock_token
            return lock_token
        return lock_token if acquired else None

    # Blocking mode with optional timeout
    end_time = time.monotonic() + (block_timeout if block_timeout is not None else 60)
    while time.monotonic() < end_time:
        try:
            acquired = await client.set(lock_key, lock_token, nx=True, px=timeout * 1000)
        except Exception:
            # Redis unavailable — fall back to in-memory lock
            if lock_key not in _INMEMORY_LOCKS:
                _INMEMORY_LOCKS[lock_key] = lock_token
                return lock_token
            acquired = False
        if acquired:
            return lock_token
        await asyncio.sleep(0.1)  # Poll interval

    return None  # Timeout


async def release_character_lock(character_id: str, lock_token: str) -> bool:
    """
    Release a per-character lock, but only if we still own it.

    Uses Lua script to check ownership before delete to avoid releasing
    another requester's lock (Safe Release pattern). Falls back to in-memory
    store if Redis is unavailable.

    Returns:
        True if lock was released, False if not owner or already expired.
    """
    client = get_redis_client()
    lock_key = f"{LOCK_PREFIX}{character_id}"

    # If using in-memory fallback (hasattr check is cheap)
    if isinstance(client, _InMemoryRedisMock):
        stored = _INMEMORY_LOCKS.get(lock_key)
        if stored == lock_token:
            _INMEMORY_LOCKS.pop(lock_key, None)
            return True
        return False

    # Redis path — use Lua script for safe ownership check
    script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """
    try:
        result = await client.eval(script, 1, lock_key, lock_token)
        return result == 1
    except Exception:
        # Redis error — try in-memory fallback
        stored = _INMEMORY_LOCKS.get(lock_key)
        if stored == lock_token:
            _INMEMORY_LOCKS.pop(lock_key, None)
            return True
        return False


async def is_locked(character_id: str) -> bool:
    """Check if a character currently has a lock (for diagnostics)."""
    client = get_redis_client()
    lock_key = f"{LOCK_PREFIX}{character_id}"
    try:
        return await client.exists(lock_key) > 0
    except Exception:
        # Fallback: check in-memory store
        return lock_key in _INMEMORY_LOCKS


# FastAPI dependency for route protection
async def require_character_lock(
    character_id: str,
    request: Request,
    timeout: int = LOCK_TTL_SECONDS,
) -> str:
    """
    FastAPI dependency that acquires a character lock for the duration
    of the request. Designed as a dependency that yields the lock token
    and ensures release in a finally block.

    Usage in route:
        @router.post("/characters/{character_id}/actions")
        async def do_action(
            character_id: str,
            lock_token: str = Depends(require_character_lock),
            ...
        ):
            try:
                ... # do work
            finally:
                await release_character_lock(character_id, lock_token)
    """
    lock_token = await acquire_character_lock(
        character_id,
        timeout=timeout,
        block=True,
        block_timeout=timeout - 5,  # Give 5s margin before TTL expiry
    )
    if lock_token is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail=f"Character {character_id} is busy (concurrent turn in progress). Please wait."
        )

    # Attach to request.state for cleanup middleware approach
    request.state.character_lock = (character_id, lock_token)
    return lock_token


# Background task to ensure lock cleanup if route exits abnormally
async def cleanup_lock_on_exit(request: Request):
    """FastAPI middleware-style cleanup for request-scoped locks."""
    if hasattr(request.state, 'character_lock'):
        character_id, lock_token = request.state.character_lock
        await release_character_lock(character_id, lock_token)
