"""D20 DM Runtime — FastAPI application.

The DM runtime sits between the player and the rules server.
It narrates, routes intent, and manages session memory.
It NEVER validates rules — the rules server is authoritative."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT
from app.routers import turn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    print(f"DM Runtime starting on {HOST}:{PORT}")
    print(f"Rules server: {app.state.rules_url if hasattr(app.state, 'rules_url') else 'not configured'}")
    yield
    print("DM Runtime shutting down")


app = FastAPI(
    title="D20 DM Runtime",
    description="Narrative interpreter for D20 Agent RPG — sits on top of the authoritative rules server",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins for hackathon demo
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
        "docs": "/docs",
        "health": "/dm/health",
    }
