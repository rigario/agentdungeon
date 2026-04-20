"""DM Runtime — Turn router.

Accepts player messages, routes to rules server, returns narrated output."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services import rules_client
from app.services.synthesis import classify_intent, synthesize_narration

router = APIRouter(prefix="/dm", tags=["dm"])


class PlayerMessage(BaseModel):
    """Incoming player message."""
    character_id: str = Field(..., description="Character ID")
    message: str = Field(..., description="Player's message or action")
    session_id: Optional[str] = Field(None, description="Session ID for continuity")


class DMTurnResponse(BaseModel):
    """DM-runtime narrated response."""
    narration: dict
    mechanics: dict
    choices: list
    server_trace: dict
    intent: dict


@router.post("/turn", response_model=DMTurnResponse)
async def dm_turn(body: PlayerMessage):
    """Process a player message through the DM runtime.

    Flow:
    1. Classify intent from player message
    2. Route to appropriate rules server endpoint
    3. Synthesize server output into narrated payload
    4. Return final player-facing response
    """
    # Step 1: Classify intent
    intent = classify_intent(body.message)

    # Step 2: Route to rules server
    try:
        if intent["server_endpoint"] == "actions":
            result = await rules_client.submit_action(
                body.character_id, intent["details"]
            )
        elif intent["server_endpoint"] == "combat":
            # Check if already in combat
            try:
                combat_state = await rules_client.get_combat(body.character_id)
                if combat_state.get("status") == "active":
                    result = await rules_client.combat_act(
                        body.character_id, intent["details"]
                    )
                else:
                    result = await rules_client.start_combat(
                        body.character_id,
                        intent.get("target", "Unknown"),
                        "[]",
                    )
            except Exception:
                # No active combat, start one
                result = await rules_client.submit_action(
                    body.character_id, intent["details"]
                )
        elif intent["server_endpoint"] == "turn":
            result = await rules_client.start_turn(
                body.character_id, {"intent": body.message}
            )
        else:
            result = await rules_client.submit_action(
                body.character_id, intent["details"]
            )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Rules server error: {str(e)}",
        )

    # Step 3: Get world context
    world_context = result.get("world_context", {})

    # Step 4: Synthesize narration
    narrated = synthesize_narration(result, intent, world_context)

    return DMTurnResponse(
        narration=narrated["narration"],
        mechanics=narrated["mechanics"],
        choices=narrated["choices"],
        server_trace=narrated["server_trace"],
        intent=intent,
    )


@router.get("/health")
async def dm_health():
    """DM runtime health check."""
    try:
        rules_health = await rules_client.health()
        return {
            "status": "healthy",
            "dm_runtime": "ok",
            "rules_server": rules_health,
        }
    except Exception as e:
        return {
            "status": "degraded",
            "dm_runtime": "ok",
            "rules_server": f"error: {str(e)}",
        }


@router.get("/character/{character_id}")
async def get_character(character_id: str):
    """Get character via DM runtime (proxied to rules server)."""
    try:
        return await rules_client.get_character(character_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/character")
async def create_character(payload: dict):
    """Create character via DM runtime (proxied to rules server)."""
    try:
        return await rules_client.create_character(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
