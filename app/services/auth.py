"""D20 Agent RPG — Auth service.

Ed25519 key management, agent registration, session utilities.
OAuth user session management.
Used by Task 1.2 (OAuth), Task 1.3 (Agent Registration), Task 2.2 (Auth Middleware).
"""

import uuid
import hashlib
import base64
import secrets
import os
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.fernet import Fernet

from app.services.database import get_db

# Encryption key for storing private keys at rest
# In production, this should come from a vault / env var
_ENCRYPTION_KEY = os.environ.get("D20_ENCRYPTION_KEY", None)
if _ENCRYPTION_KEY is None:
    _ENCRYPTION_KEY = Fernet.generate_key().decode()
    # NOTE: This means keys are lost on restart. Fine for development.
    # Production should persist this key securely.

_fernet = Fernet(_ENCRYPTION_KEY.encode() if isinstance(_ENCRYPTION_KEY, str) else _ENCRYPTION_KEY)


def generate_ed25519_keypair() -> tuple[str, str, str]:
    """Generate an Ed25519 key pair.
    
    Returns:
        (public_key_b64, private_key_b64, fingerprint)
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize to raw bytes then base64
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    pub_b64 = base64.b64encode(pub_bytes).decode()
    priv_b64 = base64.b64encode(priv_bytes).decode()
    
    # Fingerprint is SHA-256 of public key
    fingerprint = hashlib.sha256(pub_bytes).hexdigest()
    
    return pub_b64, priv_b64, fingerprint


def encrypt_private_key(private_key_b64: str) -> str:
    """Encrypt a private key for storage at rest."""
    return _fernet.encrypt(private_key_b64.encode()).decode()


def decrypt_private_key(encrypted: str) -> str:
    """Decrypt a stored private key."""
    return _fernet.decrypt(encrypted.encode()).decode()


def register_agent(user_id: str, agent_name: str) -> dict:
    """Register a new agent for a user.
    
    Args:
        user_id: The user's ID (must exist in users table, or 'dev-user' for mock mode)
        agent_name: Human-readable name for the agent
    
    Returns:
        dict with agent_id, public_key, fingerprint, private_key (one-time display)
    """
    agent_id = str(uuid.uuid4())
    pub_b64, priv_b64, fingerprint = generate_ed25519_keypair()
    encrypted_priv = encrypt_private_key(priv_b64)
    
    conn = get_db()
    try:
        # Ensure user exists (create dev user if needed for development)
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO users (id, email, display_name, oauth_provider, oauth_provider_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, f"{user_id}@dev.local", "Dev User", "dev", user_id)
            )
        
        # Insert agent
        conn.execute(
            """INSERT INTO agents (id, user_id, name, public_key, public_key_fingerprint, 
                                   private_key_encrypted, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (agent_id, user_id, agent_name, pub_b64, fingerprint, encrypted_priv)
        )
        conn.commit()
    finally:
        conn.close()
    
    return {
        "agent_id": agent_id,
        "name": agent_name,
        "public_key": pub_b64,
        "fingerprint": fingerprint,
        "private_key": priv_b64,  # One-time display!
        "warning": "Store this private key securely. It will not be shown again."
    }


def get_agent(agent_id: str) -> dict | None:
    """Get agent by ID (without private key)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, user_id, name, public_key, public_key_fingerprint, is_active, created_at "
            "FROM agents WHERE id = ?",
            (agent_id,)
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def list_agents(user_id: str) -> list[dict]:
    """List all agents for a user."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, public_key_fingerprint, is_active, created_at "
            "FROM agents WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_agent(agent_id: str, user_id: str) -> bool:
    """Soft-delete an agent (sets is_active=0). Only the owning user can delete."""
    conn = get_db()
    try:
        result = conn.execute(
            "UPDATE agents SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_id = ?",
            (agent_id, user_id)
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def create_challenge(agent_id: str) -> dict:
    """Create a challenge for agent authentication.
    
    Returns:
        dict with session_id, challenge (base64), expires_at
    """
    session_id = str(uuid.uuid4())
    challenge = secrets.token_bytes(32)
    challenge_b64 = base64.b64encode(challenge).decode()
    expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO agent_sessions (id, agent_id, challenge, expires_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, agent_id, challenge_b64, expires_at)
        )
        conn.commit()
    finally:
        conn.close()
    
    return {
        "session_id": session_id,
        "challenge": challenge_b64,
        "expires_at": expires_at
    }


def verify_challenge(session_id: str, signature_b64: str) -> dict | None:
    """Verify an agent's signed challenge.
    
    Returns:
        dict with agent_id, user_id if verified, None otherwise
    """
    conn = get_db()
    try:
        session = conn.execute(
            "SELECT * FROM agent_sessions WHERE id = ? AND is_verified = 0",
            (session_id,)
        ).fetchone()
        
        if not session:
            return None
        
        # Check expiry
        if session["expires_at"] < datetime.utcnow().isoformat():
            return None
        
        # Get agent's public key
        agent = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND is_active = 1",
            (session["agent_id"],)
        ).fetchone()
        
        if not agent:
            return None
        
        # Verify signature
        pub_bytes = base64.b64decode(agent["public_key"])
        challenge_bytes = base64.b64decode(session["challenge"])
        sig_bytes = base64.b64decode(signature_b64)
        
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        
        try:
            public_key.verify(sig_bytes, challenge_bytes)
        except Exception:
            return None
        
        # Mark session as verified
        conn.execute(
            """UPDATE agent_sessions 
               SET is_verified = 1, signature = ?, verified_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (signature_b64, session_id)
        )
        conn.commit()
        
        return {
            "agent_id": agent["id"],
            "user_id": agent["user_id"],
            "session_id": session_id
        }
    finally:
        conn.close()


# =========================================================
# USER OAUTH SESSION MANAGEMENT (Task 1.2)
# =========================================================

def find_or_create_user(
    provider: str,
    provider_id: str,
    email: str = "",
    display_name: str = "",
    avatar_url: str = "",
    access_token: str = "",
) -> dict:
    """Find existing user by OAuth provider+id, or create a new one.
    
    Returns the user record dict.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE oauth_provider = ? AND oauth_provider_id = ?",
            (provider, provider_id)
        ).fetchone()
        
        if row:
            # Update tokens and last login
            conn.execute(
                """UPDATE users 
                   SET oauth_access_token = ?, last_login_at = CURRENT_TIMESTAMP,
                       display_name = COALESCE(?, display_name),
                       avatar_url = COALESCE(?, avatar_url),
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (access_token, display_name or None, avatar_url or None, row["id"])
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
            return dict(updated)
        else:
            # Check if email already exists (dev mode fallback)
            if email:
                email_row = conn.execute(
                    "SELECT * FROM users WHERE email = ?", (email,)
                ).fetchone()
                if email_row:
                    # Update provider info and tokens
                    conn.execute(
                        """UPDATE users
                           SET oauth_provider = ?, oauth_provider_id = ?,
                               oauth_access_token = ?, last_login_at = CURRENT_TIMESTAMP,
                               display_name = COALESCE(?, display_name),
                               avatar_url = COALESCE(?, avatar_url),
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (provider, provider_id, access_token,
                         display_name or None, avatar_url or None, email_row["id"])
                    )
                    conn.commit()
                    updated = conn.execute("SELECT * FROM users WHERE id = ?", (email_row["id"],)).fetchone()
                    return dict(updated)

            # Create new user
            user_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO users 
                   (id, email, display_name, oauth_provider, oauth_provider_id,
                    oauth_access_token, avatar_url, last_login_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (user_id, email, display_name, provider, provider_id,
                 access_token, avatar_url)
            )
            conn.commit()
            return {
                "id": user_id,
                "email": email,
                "display_name": display_name,
                "oauth_provider": provider,
                "oauth_provider_id": provider_id,
                "avatar_url": avatar_url,
            }
    finally:
        conn.close()


def create_user_session(user_id: str, ip_address: str = "", user_agent: str = "") -> dict:
    """Create a user session with a bearer token.
    
    Returns dict with session_id, token, expires_at.
    """
    session_id = str(uuid.uuid4())
    token = f"user-{secrets.token_hex(32)}"
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO user_sessions (id, user_id, token, expires_at, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, token, expires_at, ip_address, user_agent)
        )
        conn.commit()
    finally:
        conn.close()
    
    return {
        "session_id": session_id,
        "token": token,
        "expires_at": expires_at,
    }


def get_user_by_token(token: str) -> dict | None:
    """Look up a user session by bearer token.
    
    Returns user dict if valid, None if expired or not found.
    """
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT u.*, s.id as session_id, s.expires_at 
               FROM user_sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token = ?""",
            (token,)
        ).fetchone()
        
        if not row:
            return None
        
        # Check expiry
        if row["expires_at"] < datetime.utcnow().isoformat():
            return None
        
        return dict(row)
    finally:
        conn.close()


def logout_user_session(token: str) -> bool:
    """Invalidate a user session by token.
    
    Returns True if a session was found and deleted.
    """
    conn = get_db()
    try:
        result = conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


# =========================================================
# AGENT RECOVERY (Task 3.2)
# =========================================================

def recover_agent(agent_id: str, user_id: str, ip_address: str = "") -> dict:
    """Recover an agent by generating new keys after user re-authenticates via OAuth.
    
    Flow:
    1. Verify user owns the agent
    2. Generate new Ed25519 key pair
    3. Update agent record (public key, fingerprint, encrypted private key)
    4. Invalidate all existing agent sessions
    5. Log recovery in agent_recovery_log
    6. Return new key pair (one-time display)
    
    Args:
        agent_id: The agent to recover
        user_id: The authenticated user (must own the agent)
        ip_address: Client IP for audit logging
    
    Returns:
        dict with agent_id, new public_key, new fingerprint, new private_key (one-time)
    
    Raises:
        ValueError: If agent not found or user doesn't own it
    """
    conn = get_db()
    try:
        # 1. Verify ownership
        agent = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND user_id = ? AND is_active = 1",
            (agent_id, user_id)
        ).fetchone()
        
        if not agent:
            raise ValueError("Agent not found or not owned by user")
        
        old_fingerprint = agent["public_key_fingerprint"]
        
        # 2. Generate new key pair
        pub_b64, priv_b64, fingerprint = generate_ed25519_keypair()
        encrypted_priv = encrypt_private_key(priv_b64)
        
        # 3. Update agent record with new keys
        conn.execute(
            """UPDATE agents 
               SET public_key = ?, public_key_fingerprint = ?, 
                   private_key_encrypted = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (pub_b64, fingerprint, encrypted_priv, agent_id)
        )
        
        # 4. Invalidate all existing agent sessions
        conn.execute(
            "UPDATE agent_sessions SET is_verified = 1 WHERE agent_id = ? AND is_verified = 0",
            (agent_id,)
        )
        # Also deactivate any agent session tokens by marking them
        conn.execute(
            """UPDATE agent_sessions 
               SET expires_at = CURRENT_TIMESTAMP 
               WHERE agent_id = ? AND expires_at > CURRENT_TIMESTAMP""",
            (agent_id,)
        )
        
        # 5. Log recovery
        recovery_token = secrets.token_urlsafe(32)
        user = conn.execute(
            "SELECT oauth_provider, oauth_provider_id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        conn.execute(
            """INSERT INTO agent_recovery_log 
               (agent_id, user_id, oauth_provider, oauth_provider_id,
                old_public_key_fingerprint, new_public_key_fingerprint,
                recovery_token, status, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
            (agent_id, user_id,
             user["oauth_provider"] if user else "unknown",
             user["oauth_provider_id"] if user else "unknown",
             old_fingerprint, fingerprint,
             recovery_token, ip_address)
        )
        
        conn.commit()
        
        return {
            "agent_id": agent_id,
            "name": agent["name"],
            "public_key": pub_b64,
            "fingerprint": fingerprint,
            "private_key": priv_b64,  # One-time display!
            "warning": "Old keys have been invalidated. Store this new private key securely. It will not be shown again.",
            "recovery_token": recovery_token,
        }
    finally:
        conn.close()


def get_recovery_log(agent_id: str) -> list[dict]:
    """Get recovery history for an agent."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, agent_id, user_id, oauth_provider, 
                      old_public_key_fingerprint, new_public_key_fingerprint,
                      status, ip_address, created_at
               FROM agent_recovery_log 
               WHERE agent_id = ? ORDER BY created_at DESC""",
            (agent_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
