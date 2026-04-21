"""DM Runtime — Turn router.

Accepts player messages, routes to rules server, returns narrated output.
Uses IntentRouter for classification + dispatch, contract schemas for type safety.
LLM-powered narration via synthesis → narrator pipeline.
"""

from fastapi import APIRouter, HTTPException

from app.contract import (
    DMResponse,
    NarrationPayload,
    MechanicsPayload,
    ChoiceOption,
    ServerTrace,
)
from app.services import rules_client
from app.services.intent_router import IntentRouter, classify_intent
from app.services.synthesis import synthesize_narration

router = APIRouter(prefix="/dm", tags=["dm"])

# Singleton router instance
_intent_router = IntentRouter(rules_client)


@router.post("/turn", response_model=DMResponse)
async def dm_turn(body: dict):
    """Process a player message through the DM runtime.

    Flow:
    1. Classify intent from player message (IntentRouter)
    2. Check for active combat → override routing
    3. Route to appropriate rules server endpoint
    4. Synthesize server output into narrated payload (LLM or passthrough)
    5. Return contract-compliant DMResponse
    """
    character_id = body.get("character_id")
    message = body.get("message", "")
    session_id = body.get("session_id")

    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")

    # Step 1-3: Route through IntentRouter (classifies, checks combat, dispatches)
    result = await _intent_router.route(character_id, message)

    # Step 4: Handle errors
    if not result.success:
        status = result.error_status or 502
        raise HTTPException(status_code=status, detail=result.error)

    # Step 5: Synthesize narration from server result (async — may use LLM)
    intent = classify_intent(message)
    intent_dict = {
        "type": intent.type.value,
        "target": intent.target,
        "details": intent.details,
        "server_endpoint": intent.server_endpoint.value,
    }
    world_context = result.world_context or {}
    narrated = await synthesize_narration(result.to_dict(), intent_dict, world_context)

    # Step 6: Build contract-compliant response
    return DMResponse(
        narration=NarrationPayload(**narrated["narration"]),
        mechanics=MechanicsPayload(**narrated["mechanics"]),
        choices=[ChoiceOption(**c) for c in narrated["choices"]],
        server_trace=ServerTrace(
            turn_id=narrated["server_trace"].get("turn_id"),
            decision_point=narrated["server_trace"].get("decision_point"),
            available_actions=narrated["server_trace"].get("available_actions", []),
            intent_used=intent_dict,
            server_endpoint_called=result.endpoint_called,
            raw_server_response_keys=list(result.raw_response.keys()),
        ),
        session_id=session_id,
    )


@router.get("/health")
async def dm_health():
    """DM runtime health check — includes rules server connectivity and narrator status."""
    from app.services.narrator import NARRATOR_ENABLED
    from app.services.dm_profile import get_status as get_dm_profile_status

    dm_profile = get_dm_profile_status()

    try:
        rules_health = await rules_client.health()
        return {
            "status": "healthy",
            "dm_runtime": "ok",
            "rules_server": rules_health,
            "intent_router": "ok",
            "narrator": {
                "enabled": NARRATOR_ENABLED,
                "api_key_set": dm_profile["api_key_set"],
                "model": dm_profile["model"],
                "mode": dm_profile["mode"],
                "hermes_profile": dm_profile["hermes_profile"],
            },
        }
    except Exception as e:
        return {
            "status": "degraded",
            "dm_runtime": "ok",
            "rules_server": f"error: {str(e)}",
            "intent_router": "ok (rules server unreachable)",
            "narrator": {
                "enabled": NARRATOR_ENABLED,
                "api_key_set": dm_profile["api_key_set"],
                "model": dm_profile["model"],
                "mode": dm_profile["mode"],
                "hermes_profile": dm_profile["hermes_profile"],
            },
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


@router.post("/intent/analyze")
async def analyze_intent(body: dict):
    """Debug endpoint — classify intent without executing.

    Useful for testing intent classification in isolation.
    """
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    intent = classify_intent(message)
    return {
        "message": message,
        "classification": {
            "type": intent.type.value,
            "target": intent.target,
            "action_type": intent.action_type,
            "details": intent.details,
            "confidence": intent.confidence,
            "server_endpoint": intent.server_endpoint.value,
        },
    }
