"""Tests for authentication middleware Ed25519 signature verification (Task 8671eae7)."""

import base64
import hashlib
import pytest
from unittest.mock import MagicMock, patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app.services.auth_middleware import AuthMiddleware
from app.main import app


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


def create_agent_in_db(conn, agent_id="test_agent", user_id="test_user"):
    """Helper: insert a test agent with Ed25519 key pair."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    pub_b64 = base64.b64encode(pub_bytes).decode()
    fingerprint = hashlib.sha256(pub_bytes).hexdigest()

    conn.execute(
        """INSERT INTO agents (id, user_id, name, public_key, public_key_fingerprint, is_active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (agent_id, user_id, "TestAgent", pub_b64, fingerprint)
    )
    conn.commit()
    return {
        "agent_id": agent_id,
        "user_id": user_id,
        "fingerprint": fingerprint,
        "private_key": private_key,
        "public_key": public_key
    }


class TestAgentSignatureVerification:
    """Verify that Agent header signature verification works correctly."""

    def test_valid_signature_authenticates(self, client):
        """A request with a valid Ed25519 signature should authenticate the agent."""
        from app.services.database import get_db
        conn = get_db()
        try:
            agent_info = create_agent_in_db(conn)
        finally:
            conn.close()

        # Construct canonical string and sign it
        method = "GET"
        path = "/characters/list"
        canonical = f"{{method}} {{path}}"
        sig_bytes = agent_info["private_key"].sign(canonical.encode("utf-8"))
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # Make request with Agent header
        headers = {
            "Authorization": f"Agent {{agent_info['fingerprint']}}:{{sig_b64}}"
        }
        response = client.get("/characters/list", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {{response.status_code}}: {{response.text}}"

    def test_invalid_signature_rejected(self, client):
        """A request with an invalid signature should be rejected (401)."""
        from app.services.database import get_db
        conn = get_db()
        try:
            agent_info = create_agent_in_db(conn)
        finally:
            conn.close()

        # Use a random invalid signature
        invalid_sig = base64.b64encode(b"not a real signature").decode()
        headers = {
            "Authorization": f"Agent {{agent_info['fingerprint']}}:{{invalid_sig}}"
        }
        response = client.get("/characters/list", headers=headers)

        assert response.status_code == 401, f"Expected 401, got {{response.status_code}}"

    def test_signature_wrong_message_rejected(self, client):
        """A signature over a different canonical string should be rejected."""
        from app.services.database import get_db
        conn = get_db()
        try:
            agent_info = create_agent_in_db(conn)
        finally:
            conn.close()

        # Sign a different method/path than what we send
        wrong_canonical = "POST /some/other/endpoint"
        sig_bytes = agent_info["private_key"].sign(wrong_canonical.encode("utf-8"))
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # Request actual GET to /characters/list
        headers = {
            "Authorization": f"Agent {{agent_info['fingerprint']}}:{{sig_b64}}"
        }
        response = client.get("/characters/list", headers=headers)

        assert response.status_code == 401, f"Expected 401 for wrong canonical string, got {{response.status_code}}"

    def test_missing_public_key_rejected(self, client):
        """An agent fingerprint with no public_key in DB should fail gracefully."""
        from app.services.database import get_db
        conn = get_db()
        try:
            # Insert agent WITHOUT public_key (simulates legacy/incomplete data)
            conn.execute(
                "INSERT INTO agents (id, user_id, name, public_key_fingerprint, is_active) "
                "VALUES (?, ?, ?, ?, 1)",
                ("bad_agent", "test_user", "BadAgent", "fake_fingerprint_1234567890abcdef")
            )
            conn.commit()
        finally:
            conn.close()

        # Attempt to auth with this agent
        fake_sig = base64.b64encode(b"ignored").decode()
        headers = {
            "Authorization": f"Agent fake_fingerprint_1234567890abcdef:{{fake_sig}}"
        }
        response = client.get("/characters/list", headers=headers)
        # Should be 401 (no auth) not 500
        assert response.status_code == 401, f"Expected 401 for missing public_key, got {{response.status_code}}"

    def test_tampered_signature_rejected(self, client):
        """Tampered signature (modified after signing) should be rejected."""
        from app.services.database import get_db
        conn = get_db()
        try:
            agent_info = create_agent_in_db(conn)
        finally:
            conn.close()

        canonical = "GET /characters/list"
        sig_bytes = agent_info["private_key"].sign(canonical.encode("utf-8"))
        # Tamper: flip a bit in the signature
        tampered = bytes([sig_bytes[0] ^ 0xFF]) + sig_bytes[1:]
        tampered_b64 = base64.b64encode(tampered).decode()

        headers = {
            "Authorization": f"Agent {{agent_info['fingerprint']}}:{{tampered_b64}}"
        }
        response = client.get("/characters/list", headers=headers)
        assert response.status_code == 401
