"""DM Runtime — Turn router.

Accepts player messages, routes to rules server, returns narrated output.
Uses formal contract schemas from app.contract for type safety."""

from fastapi import APIRouter, HTTPException

from app.contract import (
    IntentClassification,
    IntentType,
    ServerEndpoint,
    DMResponse,
    NarrationPayload,
    MechanicsPayload,
    ChoiceOption,
    ServerTrace,
    RoutingPolicy,
)
from app.services import rules_client
from app.services.synthesis import classify_intent, synthesize_narration

router = APIRouter(prefix="/dm", tags=["dm"])


@router.post("/turn", response_model=DMResponse)
async def dm_turn(body: dict):
    """Process a player message through the DM runtime.

    Flow:
    1. Classify intent from player message
    2. Route to appropriate rules server endpoint (per routing policy)
    3. Synthesize server output into narrated payload (within authority boundary)
    4. Return final player-facing response
    """
    character_id = body.get("character_id")
    message = body.get("message", "")
    session_id = body.get("session_id")

    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")

    # Step 1: Classify intent → IntentClassification
    intent = classify_intent(message)
    intent_enum = IntentType(intent["type"])
    endpoint = RoutingPolicy.get_endpoint(intent_enum)

    # Step 2: Route to rules server (per contract routing policy)
    try:
        if endpoint == ServerEndpoint.ACTIONS:
            result = await rules_client.submit_action(character_id, intent["details"])
        elif endpoint == ServerEndpoint.COMBAT:
            try:
                combat_state = await rules_client.get_combat(character_id)
                if combat_state.get("status") == "active":
                    result = await rules_client.combat_act(character_id, intent["details"])
                else:
                    result = await rules_client.start_combat(
                        character_id, intent.get("target", "Unknown"), "[]"
                    )
            except Exception:
                result = await rules_client.submit_action(character_id, intent["details"])
        elif endpoint == ServerEndpoint.TURN:
            result = await rules_client.start_turn(character_id, {"intent": message})
        else:
            result = await rules_client.submit_action(character_id, intent["details"])
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Rules server error: {str(e)}",
        )

    # Step 3: Synthesize narration (within authority boundary)
    world_context = result.get("world_context", {})
    narrated = synthesize_narration(result, intent, world_context)

    # Step 4: Build contract-compliant response
    return DMResponse(
        narration=NarrationPayload(**narrated["narration"]),
        mechanics=MechanicsPayload(**narrated["mechanics"]),
        choices=[ChoiceOption(**c) for c in narrated["choices"]],
        server_trace=ServerTrace(
            turn_id=narrated["server_trace"].get("turn_id"),
            decision_point=narrated["server_trace"].get("decision_point"),
            available_actions=narrated["server_trace"].get("available_actions", []),
            intent_used=intent,
            server_endpoint_called=endpoint.value,
            raw_server_response_keys=list(result.keys()),
        ),
        session_id=session_id,
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
