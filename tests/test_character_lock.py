"""Tests for per-character DM request queuing (concurrency protection).

Validates that concurrent turn requests for the same character are serialized
via Redis-based distributed locking.
"""

import sys
import os
import asyncio
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import redis.asyncio as redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Unit tests for character_lock module
# ---------------------------------------------------------------------------

class TestCharacterLockUnit:
    """Direct tests of the lock service using a mocked Redis client."""

    @pytest.fixture
    def mock_redis(self, monkeypatch):
        """Create a mock Redis client that simulates SET NX operations."""
        client = AsyncMock()
        client.set = AsyncMock()
        client.eval = AsyncMock()
        client.exists = AsyncMock()
        yield client

    @pytest.fixture
    def lock_service(self, mock_redis, monkeypatch):
        """Patch get_redis_client to return our mock."""
        monkeypatch.setattr('app.services.character_lock.get_redis_client', lambda: mock_redis)
        monkeypatch.setattr('app.services.character_lock.REDIS_URL', 'redis://test:6379/0')
        from app.services import character_lock as cl
        yield cl
        # Cleanup module-level _redis_client
        cl._redis_client = None

    async def test_acquire_lock_success(self, lock_service, mock_redis):
        """Lock acquisition succeeds on first try."""
        mock_redis.set.return_value = True
        token = await lock_service.acquire_character_lock("char-123", timeout=30)
        assert token is not None
        mock_redis.set.assert_called_once_with(
            "d20:dm_lock:char-123", token, nx=True, px=30000
        )

    async def test_acquire_lock_failure_nonblocking(self, lock_service, mock_redis):
        """Non-blocking acquisition fails if lock held."""
        mock_redis.set.return_value = False
        token = await lock_service.acquire_character_lock("char-123", block=False)
        assert token is None

    async def test_acquire_lock_blocking_success_quick(self, lock_service, mock_redis):
        """Blocking acquisition succeeds after brief wait."""
        # First call fails, second succeeds
        mock_redis.set.side_effect = [False, True]
        token = await lock_service.acquire_character_lock("char-123", block=True, block_timeout=1.0)
        assert token is not None
        assert mock_redis.set.call_count == 2

    async def test_acquire_lock_blocking_timeout(self, lock_service, mock_redis):
        """Blocking acquisition times out if lock never free."""
        mock_redis.set.return_value = False
        token = await lock_service.acquire_character_lock("char-123", block=True, block_timeout=0.2)
        assert token is None
        # Should have multiple attempts
        assert mock_redis.set.call_count > 1

    async def test_release_lock_success(self, lock_service, mock_redis):
        """Releasing a lock you own succeeds."""
        mock_redis.eval.return_value = 1  # Script returns 1 (deleted)
        token = "test-token-xyz"
        success = await lock_service.release_character_lock("char-123", token)
        assert success is True
        mock_redis.eval.assert_called_once()

    async def test_release_lock_not_owner(self, lock_service, mock_redis):
        """Release fails if lock held by someone else."""
        mock_redis.eval.return_value = 0  # Value didn't match
        token = "wrong-token"
        success = await lock_service.release_character_lock("char-123", token)
        assert success is False

    async def test_is_locked(self, lock_service, mock_redis):
        """Check if character has active lock."""
        mock_redis.exists.return_value = 1
        assert await lock_service.is_locked("char-123") is True
        mock_redis.exists.assert_called_once_with("d20:dm_lock:char-123")

        mock_redis.exists.return_value = 0
        assert await lock_service.is_locked("char-456") is False


# ---------------------------------------------------------------------------
# Integration test: verify endpoint uses lock (mock Redis)
# ---------------------------------------------------------------------------

class TestActionEndpointLocking:
    """Test that submit_action endpoint acquires and releases character lock."""

    @pytest.fixture
    def mock_lock_acquire(self, monkeypatch):
        """Mock acquire_character_lock to track calls and simulate blocking."""
        call_log = []

        async def mock_acquire(char_id, timeout=25, block=True, block_timeout=None):
            call_log.append(("acquire", char_id))
            # Simulate lock granted
            token = str(uuid.uuid4())
            call_log.append(("granted", token))
            return token

        monkeypatch.setattr('app.routers.actions.acquire_character_lock', mock_acquire)
        return call_log

    @pytest.fixture
    def mock_lock_release(self, monkeypatch):
        """Mock release_character_lock to track calls."""
        released = []

        async def mock_release(char_id, token):
            released.append((char_id, token))

        monkeypatch.setattr('app.routers.actions.release_character_lock', mock_release)
        return released

    # Note: Full endpoint integration test requires full app TestClient, DB,
    # and possibly DM mocking. We'll do a lightweight test ensuring the
    # dependency injection pattern resolves correctly.

    def test_lock_acquire_release_called(self, mock_lock_acquire, mock_lock_release):
        """Smoke: verify lock functions would be called by route (needs full TestClient)."""
        # This is a placeholder to document intent. Full E2E test would:
        # 1. Start TestClient(app)
        # 2. Patch character_lock functions
        # 3. Make request to /characters/{id}/actions
        # 4. Assert acquire was called with char_id
        # 5. Assert release was called with char_id and token in finally
        pass


# ---------------------------------------------------------------------------
# Concurrency stress test (requires running Redis - marked as integration)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCharacterLockConcurrency:
    """Real Redis-backed concurrency tests. Requires redis server."""

    @pytest.fixture(scope="class")
    async def redis_client(self):
        """Create a real Redis client for testing."""
        client = redis.from_url("redis://localhost:6379/1")  # test db
        try:
            await client.ping()
            yield client
        except Exception:
            pytest.skip("Redis not available")
        finally:
            await client.close()

    async def test_concurrent_locks_serialized(self, redis_client):
        """Only one request should hold lock at a time."""
        from app.services.character_lock import acquire_character_lock, release_character_lock

        char_id = "test-concurrent-char"
        lock_prefix = "d20:dm_lock:"

        # Clean any stale locks
        await redis_client.delete(f"{lock_prefix}{char_id}")

        async def worker(n: int):
            token = await acquire_character_lock(char_id, timeout=5, block=True, block_timeout=3)
            assert token is not None, f"Worker {n} failed to acquire"
            # Verify exclusive ownership
            assert await redis_client.get(f"{lock_prefix}{char_id}") == token
            await asyncio.sleep(0.2)  # hold briefly
            await release_character_lock(char_id, token)
            return n

        # Launch 5 concurrent workers
        results = await asyncio.gather(*[worker(i) for i in range(5)])
        assert len(results) == 5
        # Lock should be free after all done
        assert await redis_client.exists(f"{lock_prefix}{char_id}") == 0
