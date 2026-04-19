"""D20 Agent RPG — Auth Router.

Endpoints for:
- Task 1.2: OAuth user login (Google, X/Twitter), session management
- Task 1.3: Agent registration, listing, deletion, and challenge-response auth
"""

from fastapi import APIRouter, HTTPException, Header, Request, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import secrets
import uuid

from app.config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
    TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET,
    BASE_URL, OAUTH_DEV_MODE,
)
from app.services.auth import (
    register_agent,
    get_agent,
    list_agents,
    delete_agent,
    create_challenge,
    verify_challenge,
    find_or_create_user,
    create_user_session,
    get_user_by_token,
    logout_user_session,
    recover_agent,
    get_recovery_log,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# =========================================================
# OAUTH ENDPOINTS (Task 1.2)
# =========================================================

# ---- Dev-mode mock login page ----

_LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html><head><title>D20 — Login</title>
<style>
  body {{ font-family: system-ui; background: #1a1a2e; color: #e0e0e0; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
  .card {{ background: #16213e; border-radius: 12px; padding: 2rem; max-width: 400px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,.4); }}
  h1 {{ color: #e94560; margin-bottom: .5rem; }}
  p {{ color: #a0a0b0; margin-bottom: 1.5rem; }}
  .btn {{ display: block; width: 100%; padding: .75rem; margin: .5rem 0; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; text-decoration: none; color: #fff; }}
  .btn-google {{ background: #4285f4; }}
  .btn-twitter {{ background: #1da1f2; }}
  .btn:hover {{ opacity: .85; }}
  .dev-badge {{ font-size: .75rem; background: #e94560; padding: 2px 8px; border-radius: 4px; margin-left: .5rem; }}
  input {{ width: 90%; padding: .5rem; margin: .25rem 0; border-radius: 6px; border: 1px solid #333; background: #0f3460; color: #e0e0e0; }}
</style></head><body>
<div class="card">
  <h1>🐉 The Dreaming Hunger <span class="dev-badge">DEV</span></h1>
  <p>Sign in to claim your character</p>
  <form method="get" action="/auth/oauth/{provider}/callback">
    <input name="display_name" placeholder="Display name" value="Adventurer" required />
    <input name="email" placeholder="Email (optional)" type="email" />
    <input type="hidden" name="state" value="{state}" />
    <input type="hidden" name="code" value="mock-code" />
    <button class="btn btn-google" type="submit" formaction="/auth/oauth/google/callback">Sign in with Google</button>
    <button class="btn btn-twitter" type="submit" formaction="/auth/oauth/twitter/callback">Sign in with X</button>
  </form>
</div>
</body></html>"""


@router.get("/oauth/google/login")
async def google_login(request: Request):
    """Start Google OAuth flow. Redirects to Google or shows dev login page."""
    state = secrets.token_urlsafe(32)
    if not OAUTH_DEV_MODE and GOOGLE_CLIENT_ID:
        redirect_uri = f"{BASE_URL}/auth/oauth/google/callback"
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={GOOGLE_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope=openid%20email%20profile"
            f"&state={state}"
        )
        return RedirectResponse(auth_url)
    else:
        return HTMLResponse(_LOGIN_PAGE_HTML.format(provider="google", state=state))


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    display_name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
):
    """Handle Google OAuth callback. Creates user + session, redirects to character sheet."""
    if not code:
        raise HTTPException(400, "Missing authorization code")
    
    if OAUTH_DEV_MODE or not GOOGLE_CLIENT_ID:
        # Dev mode: use the form data directly
        provider_id = str(uuid.uuid4())
        dn = display_name or "Dev Adventurer"
        em = email or f"{provider_id[:8]}@dev.local"
        access_token = ""
    else:
        # Real mode: exchange code for token, fetch user info
        import httpx
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{BASE_URL}/auth/oauth/google/callback",
                    "grant_type": "authorization_code",
                },
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")
            
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_data = user_resp.json()
            provider_id = user_data.get("id", "")
            dn = user_data.get("name", "Adventurer")
            em = user_data.get("email", "")
    
    # Find or create user
    user = find_or_create_user(
        provider="google",
        provider_id=provider_id,
        email=em,
        display_name=dn,
        access_token=access_token,
    )
    
    # Create session
    session = create_user_session(
        user_id=user["id"],
        ip_address=request.client.host if request.client else "",
    )
    
    # Redirect with token (in production, set cookie instead)
    return {
        "status": "authenticated",
        "provider": "google",
        "user": {
            "id": user["id"],
            "display_name": user.get("display_name", dn),
            "email": user.get("email", em),
        },
        "session": {
            "token": session["token"],
            "expires_at": session["expires_at"],
        },
    }


@router.get("/oauth/twitter/login")
async def twitter_login(request: Request):
    """Start X/Twitter OAuth flow. Redirects to X or shows dev login page."""
    state = secrets.token_urlsafe(32)
    if not OAUTH_DEV_MODE and TWITTER_CLIENT_ID:
        redirect_uri = f"{BASE_URL}/auth/oauth/twitter/callback"
        auth_url = (
            f"https://twitter.com/i/oauth2/authorize"
            f"?client_id={TWITTER_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope=tweet.read%20users.read"
            f"&state={state}"
            f"&code_challenge=challenge"
            f"&code_challenge_method=plain"
        )
        return RedirectResponse(auth_url)
    else:
        return HTMLResponse(_LOGIN_PAGE_HTML.format(provider="twitter", state=state))


@router.get("/oauth/twitter/callback")
async def twitter_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    display_name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
):
    """Handle X/Twitter OAuth callback. Creates user + session."""
    if not code:
        raise HTTPException(400, "Missing authorization code")
    
    if OAUTH_DEV_MODE or not TWITTER_CLIENT_ID:
        provider_id = str(uuid.uuid4())
        dn = display_name or "Dev Adventurer"
        em = email or f"{provider_id[:8]}@dev.local"
        access_token = ""
    else:
        import httpx
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "code": code,
                    "client_id": TWITTER_CLIENT_ID,
                    "client_secret": TWITTER_CLIENT_SECRET,
                    "redirect_uri": f"{BASE_URL}/auth/oauth/twitter/callback",
                    "grant_type": "authorization_code",
                    "code_verifier": "challenge",
                },
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")
            
            user_resp = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_data = user_resp.json().get("data", {})
            provider_id = user_data.get("id", "")
            dn = user_data.get("name", "Adventurer")
            em = ""
    
    user = find_or_create_user(
        provider="twitter",
        provider_id=provider_id,
        email=em,
        display_name=dn,
        access_token=access_token,
    )
    
    session = create_user_session(
        user_id=user["id"],
        ip_address=request.client.host if request.client else "",
    )
    
    return {
        "status": "authenticated",
        "provider": "twitter",
        "user": {
            "id": user["id"],
            "display_name": user.get("display_name", dn),
            "email": user.get("email", em),
        },
        "session": {
            "token": session["token"],
            "expires_at": session["expires_at"],
        },
    }


class LogoutRequest(BaseModel):
    token: Optional[str] = None


@router.post("/logout")
async def logout(
    body: LogoutRequest = LogoutRequest(),
    authorization: Optional[str] = Header(None),
):
    """Invalidate user session. Pass token in body or Authorization header."""
    token = body.token
    if not token and authorization:
        token = authorization.replace("Bearer ", "")
    if not token:
        raise HTTPException(400, "No token provided")
    
    success = logout_user_session(token)
    if success:
        return {"status": "logged_out"}
    else:
        raise HTTPException(404, "Session not found")


@router.get("/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current authenticated user from bearer token."""
    if not authorization:
        raise HTTPException(401, "No authorization header")
    
    token = authorization.replace("Bearer ", "")
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    
    return {
        "id": user["id"],
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "oauth_provider": user.get("oauth_provider"),
        "avatar_url": user.get("avatar_url"),
        "last_login_at": user.get("last_login_at"),
    }


# ---- Agent endpoints (Task 1.3) ----


# ---- Request/Response Models ----

class RegisterAgentRequest(BaseModel):
    name: str
    user_id: Optional[str] = None  # Defaults to dev-user for hackathon


class RegisterAgentResponse(BaseModel):
    agent_id: str
    name: str
    public_key: str
    fingerprint: str
    private_key: str
    warning: str


class AgentInfoResponse(BaseModel):
    id: str
    user_id: str
    name: str
    public_key: str
    public_key_fingerprint: str
    is_active: int
    created_at: str


class ChallengeRequest(BaseModel):
    agent_id: str


class ChallengeResponse(BaseModel):
    session_id: str
    challenge: str
    expires_at: str


class VerifyRequest(BaseModel):
    session_id: str
    signature: str


class VerifyResponse(BaseModel):
    agent_id: str
    user_id: str
    session_id: str
    token: str  # Simple bearer token for the session


# ---- Helper for extracting user_id from headers ----

def get_user_id(x_user_id: Optional[str] = None) -> str:
    """Extract user_id from header, defaulting to dev-user for hackathon."""
    return x_user_id or "dev-user"


# ---- Endpoints ----

@router.post("/agents/register", response_model=RegisterAgentResponse, status_code=201)
async def api_register_agent(body: RegisterAgentRequest, x_user_id: Optional[str] = Header(None)):
    """Register a new agent. Generates Ed25519 key pair.
    
    The private key is returned ONCE in this response. Store it securely.
    In dev mode, user_id defaults to 'dev-user'.
    """
    user_id = get_user_id(x_user_id)
    if not body.name or len(body.name.strip()) == 0:
        raise HTTPException(400, "Agent name is required")
    
    result = register_agent(user_id, body.name.strip())
    return RegisterAgentResponse(**result)


@router.get("/agents", response_model=list[dict])
async def api_list_agents(x_user_id: Optional[str] = Header(None)):
    """List all agents for the current user."""
    user_id = get_user_id(x_user_id)
    return list_agents(user_id)


@router.get("/agents/{agent_id}")
async def api_get_agent(agent_id: str):
    """Get agent details (public info only, no private key)."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.delete("/agents/{agent_id}")
async def api_delete_agent(agent_id: str, x_user_id: Optional[str] = Header(None)):
    """Soft-delete an agent (sets is_active=0)."""
    user_id = get_user_id(x_user_id)
    success = delete_agent(agent_id, user_id)
    if not success:
        raise HTTPException(404, "Agent not found or not owned by user")
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/agents/challenge", response_model=ChallengeResponse)
async def api_create_challenge(body: ChallengeRequest):
    """Create an authentication challenge for an agent.
    
    The agent must sign this challenge with their private key to authenticate.
    """
    agent = get_agent(body.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if not agent["is_active"]:
        raise HTTPException(403, "Agent is deactivated")
    
    result = create_challenge(body.agent_id)
    return ChallengeResponse(**result)


@router.post("/agents/verify", response_model=VerifyResponse)
async def api_verify_challenge(body: VerifyRequest):
    """Verify an agent's signed challenge to complete authentication.
    
    Returns a session token that can be used for authenticated requests.
    """
    result = verify_challenge(body.session_id, body.signature)
    if not result:
        raise HTTPException(401, "Invalid signature or expired challenge")
    
    # Generate a simple bearer token for this session
    import secrets
    token = f"agent-{secrets.token_hex(32)}"
    
    return VerifyResponse(
        agent_id=result["agent_id"],
        user_id=result["user_id"],
        session_id=result["session_id"],
        token=token,
    )


# =========================================================
# AGENT RECOVERY ENDPOINTS (Task 3.2)
# =========================================================


class RecoverAgentRequest(BaseModel):
    """Request body for agent recovery. User must provide session token to prove re-authentication."""
    session_token: str  # Fresh OAuth session token (user must have logged in recently)


class RecoverAgentResponse(BaseModel):
    agent_id: str
    name: str
    public_key: str
    fingerprint: str
    private_key: str
    warning: str
    recovery_token: str


@router.post("/agents/{agent_id}/recover", response_model=RecoverAgentResponse)
async def api_recover_agent(
    agent_id: str,
    body: RecoverAgentRequest,
    request: Request,
    x_user_id: Optional[str] = Header(None),
):
    """Recover an agent after user re-authenticates via social OAuth.
    
    Generates a new Ed25519 key pair for the agent. Old keys are invalidated.
    The new private key is returned ONCE — store it securely.
    
    Requirements:
    - User must be authenticated (provide session_token from fresh OAuth login)
    - User must own the agent
    - Recovery is logged in agent_recovery_log for audit
    
    Security:
    - Old agent sessions are invalidated
    - Recovery is logged with IP, provider, old/new key fingerprints
    """
    # Validate the session token belongs to a real user
    user = get_user_by_token(body.session_token)
    if not user:
        raise HTTPException(401, "Invalid or expired session token. Please re-authenticate via OAuth.")
    
    # Use user_id from the validated session (ignore x_user_id header for security)
    user_id = user["id"]
    
    try:
        result = recover_agent(
            agent_id=agent_id,
            user_id=user_id,
            ip_address=request.client.host if request.client else "",
        )
        return RecoverAgentResponse(**result)
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.get("/agents/{agent_id}/recover/log")
async def api_get_recovery_log(
    agent_id: str,
    x_user_id: Optional[str] = Header(None),
):
    """Get recovery history for an agent. Only the owning user can view."""
    user_id = get_user_id(x_user_id)
    
    # Verify ownership
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if agent["user_id"] != user_id:
        raise HTTPException(403, "You don't own this agent")
    
    return get_recovery_log(agent_id)
