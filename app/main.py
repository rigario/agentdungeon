"""Rigario D20 Agent RPG — DM Server."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from app.config import HOST, PORT
from app.services.database import init_db
from app.services.auth_middleware import AuthMiddleware
from app.routers import health, characters, events, actions, combat, turns, narrative, items, auth, npcs, map as map_router
from app.routers.combat import approval_router
from app.routers import narrative_introspect
from app.routers import time as time_router
from app.routers import cadence as cadence_router
from app.routers import portal as portal_router
from app.routers import dm_sessions
from app.services.cadence_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and start background cadence scheduler."""
    init_db()
    print(f"[D20] Database initialized")

    # Clean up stale active combats from previous crashes
    from app.services.combat_cleanup import cleanup_stale_combats
    result = cleanup_stale_combats()
    if result["resolved"]:
        print(f"[D20][Startup] Combat cleanup: resolved {result['resolved']} stale combat(s)")
        for detail in result["details"]:
            print(f"  [D20]  {detail}")
    else:
        print(f"[D20][Startup] No stale combats found — all clear")

    # Start cadence background scheduler
    start_scheduler(app)

    yield

    # Shut down scheduler on app exit
    stop_scheduler(app)
    print(f"[D20] Server shutting down")


app = FastAPI(
    title="Rigario D20 Agent RPG",
    description="DM server for agent-led D&D 5E idle RPG. Validates rules, runs encounters, tracks world state.",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth middleware — extracts user/agent identity from headers
app.add_middleware(AuthMiddleware)

# Static files — character sheet UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Character sheet routes
@app.get("/")
def serve_index():
    """Serve the landing page."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/demo")
def serve_demo():
    """Serve the demo walkthrough page."""
    return FileResponse(os.path.join(static_dir, "demo.html"))


@app.get("/map")
def serve_map():
    """Serve the world map HTML page."""
    return FileResponse(os.path.join(static_dir, "map.html"))


@app.get("/characters/{character_id}/sheet")
def character_sheet_redirect(character_id: str):
    """Redirect to the character sheet viewer with the character ID."""
    return RedirectResponse(url=f"/sheet?id={character_id}")


@app.get("/sheet")
def serve_character_sheet():
    """Serve the character sheet HTML page."""
    return FileResponse(os.path.join(static_dir, "character-sheet.html"))


@app.get("/cutscenes")
def serve_cutscenes():
    """Serve the standalone cutscenes page (opening + ending)."""
    return FileResponse(os.path.join(static_dir, "cutscenes.html"))


@app.get("/npcs-page")
def serve_npcs_page():
    """Serve the NPC gallery page — fetches from /npcs API."""
    return FileResponse(os.path.join(static_dir, "npcs.html"))


@app.get("/npc")
def redirect_npcs_to_gallery():
    """Redirect /npcs to the NPC gallery page (user-friendly URL)."""
    return RedirectResponse(url="/npcs-page", status_code=302)


@app.get("/items-page")
def serve_items_page():
    """Serve the items catalogue page — fetches from /items API."""
    return FileResponse(os.path.join(static_dir, "items.html"))

# Register routers
app.include_router(health.router)
app.include_router(characters.router)
app.include_router(events.router)
app.include_router(actions.router)
app.include_router(combat.router)
app.include_router(approval_router)
app.include_router(turns.router)
app.include_router(narrative.router)
app.include_router(items.router)
app.include_router(npcs.router)
app.include_router(auth.router)
app.include_router(map_router.router)
app.include_router(narrative_introspect.router, prefix="/narrative-introspect", tags=["narrative-introspect"])
app.include_router(time_router.router)
app.include_router(cadence_router.router)
app.include_router(portal_router.router)
app.include_router(dm_sessions.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
