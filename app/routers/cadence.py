"""D20 Agent RPG — Playtest Cadence API.

Endpoints for toggling playtest mode, advancing doom clock ticks,
and querying cadence status. Used by agent heartbeats and the DM
runtime to control accelerated playtest pacing.

Routes:
  GET  /cadence/status             — full cadence system status
  POST /cadence/toggle             — toggle between normal/playtest mode
  POST /cadence/config             — update tick interval
  POST /cadence/tick/{char_id}     — advance doom clock by one tick
  GET  /cadence/doom/{char_id}     — get doom clock state for a character
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from app.services.playtest_cadence import (
    get_cadence_status,
    set_cadence_mode,
    set_tick_interval,
    advance_tick,
    get_doom_clock,
    get_config,
    DEFAULT_TICK_INTERVAL_SECONDS,
)
from app.services.auth_helpers import get_auth

router = APIRouter(prefix="/cadence", tags=["cadence"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CadenceToggle(BaseModel):
    mode: str = Field(..., description="'normal' or 'playtest'")
    tick_interval_seconds: Optional[int] = Field(
        None, description="Tick interval in seconds (playtest mode only). Min 30."
    )


class CadenceConfig(BaseModel):
    tick_interval_seconds: int = Field(
        ..., description="New tick interval in seconds. Min 30."
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
def cadence_status():
    """Get full cadence system status — mode, config, global stats."""
    return get_cadence_status()


@router.post("/toggle")
def toggle_cadence(body: CadenceToggle):
    """Toggle between normal and playtest cadence mode.

    Playtest mode enables accelerated 3-5 minute ticks and doom clock
    progression. Normal mode disables all accelerated mechanics.
    """
    try:
        config = set_cadence_mode(body.mode, body.tick_interval_seconds)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "ok": True,
        "message": f"Cadence mode set to '{body.mode}'"
                   + (f" with {config['tick_interval_seconds']}s ticks" if body.mode == "playtest" else ""),
        "config": config,
    }


@router.post("/config")
def update_config(body: CadenceConfig):
    """Update tick interval without changing mode."""
    try:
        config = set_tick_interval(body.tick_interval_seconds)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "ok": True,
        "message": f"Tick interval set to {body.tick_interval_seconds}s",
        "config": config,
    }


@router.post("/tick/{character_id}")
def tick(character_id: str):
    """Advance the doom clock by one tick for a character.

    Only works in playtest mode. Increments the tick counter and may
    trigger front portent advancement if thresholds are crossed.
    Returns the updated doom clock state plus any triggered events.
    """
    result = advance_tick(character_id)
    if "error" in result:
        raise HTTPException(409, result["error"])
    return result


@router.get("/doom/{character_id}")
def doom_status(character_id: str):
    """Get doom clock state for a character."""
    return get_doom_clock(character_id)
