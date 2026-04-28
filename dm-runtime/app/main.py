"""D20 DM Runtime — FastAPI application.

The DM runtime sits between the player and the rules server.
It narrates, routes intent, and manages session memory.
It NEVER validates rules — the rules server is authoritative.

Contract: see app.contract for formal payload schemas and authority boundaries.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT
from app.contract import CONTRACT_VERSION, CONTRACT_DOC, AuthorityBoundary, RoutingPolicy
from app.routers import turn
import httpx
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    print(f"DM Runtime starting on {HOST}:{PORT}")
    print(f"Contract version: {CONTRACT_VERSION}")
    print(f"Rules server: {app.state.rules_url if hasattr(app.state, 'rules_url') else 'not configured'}")

    # Initialize shared HTTP client with connection pooling for Kimi API calls
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    app.state.http_client = httpx.AsyncClient(
        timeout=60.0,
        limits=limits,
        headers={"User-Agent": "d20-dm-runtime/1.0"}
    )
    logger.info("Shared HTTP client initialized with connection pooling")

    # Wire shared client into dm_profile for connection reuse
    from app.services import dm_profile
    dm_profile.set_http_client(app.state.http_client)

    yield

    # Cleanup: close HTTP client
    if hasattr(app.state, "http_client"):
        await app.state.http_client.aclose()
        logger.info("HTTP client closed")
    print("DM Runtime shutting down")


app = FastAPI(
    title="D20 DM Runtime",
    description="Narrative interpreter for D20 Agent RPG — sits on top of the authoritative rules server",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins for public demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(turn.router)


@app.get("/")
async def root():
    return {
        "service": "d20-dm-runtime",
        "version": "0.1.0",
        "contract_version": CONTRACT_VERSION,
        "docs": "/docs",
        "health": "/dm/health",
        "contract": "/dm/contract",
    }


@app.get("/dm/contract")
async def get_contract():
    """Expose the DM runtime contract for introspection.

    Returns authority boundaries, routing policy, and contract version.
    Useful for debugging, validation, and player-agent onboarding.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "reference_doc": CONTRACT_DOC,
        "authority": {
            "dm_owns": sorted(AuthorityBoundary.DM_OWNED),
            "server_owns": sorted(AuthorityBoundary.SERVER_OWNED),
            "forbidden": sorted(AuthorityBoundary.FORBIDDEN),
        },
        "routing": {
            "sync": {k.value: v.value for k, v in RoutingPolicy.SYNC_ENDPOINTS.items()},
            "async": {k.value: v.value for k, v in RoutingPolicy.ASYNC_ENDPOINTS.items()},
        },
        "invariant": "The DM runtime is not the game engine. It is the narrative interpreter sitting on top of an authoritative rules server.",
    }
