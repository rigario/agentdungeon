"""DM Runtime — Turn router.

Accepts player messages, routes to rules server, returns narrated output.
Uses IntentRouter for classification + dispatch, contract schemas for type safety.
LLM-powered narration via synthesis → narrator pipeline.
"""

from fastapi import APIRouter, HTTPException

from app.contract import DMResponse, NarrationPayload, MechanicsPayload, ChoiceOption, ServerTrace
from app.services import rules_client
from app.services.intent_router import IntentRouter, classify_intent
from app.services.character_validation import validate_character_for_turn
from app.services.synthesis import synthesize_narration

router = APIRouter(prefix="/dm", tags=["dm"])
_intent_router = IntentRouter(rules_client)


@router.post("/turn", response_model=DMResponse)
async def dm_turn(body: dict):
    character_id = body.get("character_id")
    message = body.get("message", "")
    session_id = body.get("session_id")

    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")

    try:
        validation = await validate_character_for_turn(character_id)
        if not validation.get("valid"):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "character_state_invalid",
                    "reason": validation.get("reason"),
                    "code": validation.get("code"),
                    "checks_run": validation.get("checks_run", []),
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Validation error: {str(e)}")

    result = await _intent_router.route(character_id, message)
    if not result.success:
        status = result.error_status or 502
        raise HTTPException(status_code=status, detail=result.error)

    try:
        intent = classify_intent(message)
        intent_dict = {
            "type": intent.type.value,
            "target": intent.target,
            "details": intent.details,
            "server_endpoint": intent.server_endpoint.value,
        }
        world_context = result.world_context or {}
        narrated = await synthesize_narration(result.to_dict(), intent_dict, world_context, session_id=session_id)
        resolved_session_id = narrated.get("session_id") or session_id

        return DMResponse(
            narration=NarrationPayload(**narrated["narration"]),
            mechanics=MechanicsPayload(**narrated["mechanics"]),
            choices=[ChoiceOption(**c) for c in narrated["choices"]],
            server_trace=ServerTrace(
                turn_id=narrated["server_trace"].get("turn_id"),
                decision_point=narrated["server_trace"].get("decision_point"),
                available_actions=narrated["server_trace"].get("available_actions", []),
                combat_log=narrated["server_trace"].get("combat_log", []),
                intent_used=intent_dict,
                server_endpoint_called=result.endpoint_called,
                raw_server_response_keys=list(result.raw_response.keys()),
            ),
            session_id=resolved_session_id,
        )
    except Exception as e:
        logger.exception("dm_turn unexpected error")
        raise HTTPException(status_code=502, detail=f"DM processing error: {str(e)}")


@router.post("/narrate", response_model=DMResponse)
async def dm_narrate(body: dict):
    """Narrate an already-resolved rules-server result.

    This endpoint is intentionally narrate-only. It does not acquire the
    character action lock, classify into another rules action, or call the
    rules server. It is safe for the rules server to call from /actions after
    mechanics have already been resolved.
    """
    character_id = body.get("character_id")
    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")

    resolved_result = body.get("resolved_result") or body.get("server_result")
    if not isinstance(resolved_result, dict):
        raise HTTPException(status_code=400, detail="resolved_result is required")

    message = body.get("player_message") or body.get("message", "")
    session_id = body.get("session_id")
    world_context = body.get("world_context") or {}

    intent = classify_intent(message)
    intent_dict = {
        "type": intent.type.value,
        "target": intent.target,
        "details": intent.details,
        "server_endpoint": intent.server_endpoint.value,
    }

    narrated = await synthesize_narration(resolved_result, intent_dict, world_context, session_id=session_id)
    resolved_session_id = narrated.get("session_id") or session_id

    return DMResponse(
        narration=NarrationPayload(**narrated["narration"]),
        mechanics=MechanicsPayload(**narrated["mechanics"]),
        choices=[ChoiceOption(**c) for c in narrated["choices"]],
        server_trace=ServerTrace(
            turn_id=narrated["server_trace"].get("turn_id"),
            decision_point=narrated["server_trace"].get("decision_point"),
            available_actions=narrated["server_trace"].get("available_actions", []),
            combat_log=narrated["server_trace"].get("combat_log", []),
            intent_used=intent_dict,
            server_endpoint_called="narrate",
            raw_server_response_keys=list(resolved_result.keys()),
        ),
        session_id=resolved_session_id,
    )


@router.get("/health")
async def dm_health():
    from app.services.narrator import NARRATOR_ENABLED
    from app.services.dm_profile import get_status as get_dm_profile_status

    dm_profile = get_dm_profile_status()

    try:
        rules_health = await rules_client.health()
        status = "healthy" if dm_profile.get("runtime_ready") else "degraded"
        return {
            "status": status,
            "dm_runtime": "ok",
            "rules_server": rules_health,
            "intent_router": "ok",
            "narrator": {
                "enabled": NARRATOR_ENABLED,
                "api_key_set": dm_profile["api_key_set"],
                "model": dm_profile["model"],
                "mode": dm_profile["mode"],
                "hermes_profile": dm_profile["hermes_profile"],
                "hermes_home": dm_profile["hermes_home"],
                "hermes_binary": dm_profile["hermes_binary"],
                "binary_ok": dm_profile["binary_ok"],
                "binary_help_ok": dm_profile["binary_help_ok"],
                "profile_exists": dm_profile["profile_exists"],
                "runtime_ready": dm_profile["runtime_ready"],
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
                "hermes_home": dm_profile["hermes_home"],
                "hermes_binary": dm_profile["hermes_binary"],
                "binary_ok": dm_profile["binary_ok"],
                "binary_help_ok": dm_profile["binary_help_ok"],
                "profile_exists": dm_profile["profile_exists"],
                "runtime_ready": dm_profile["runtime_ready"],
            },
        }


@router.get("/character/{character_id}")
async def get_character(character_id: str):
    try:
        return await rules_client.get_character(character_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/character")
async def create_character(payload: dict):
    try:
        return await rules_client.create_character(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/intent/analyze")
async def analyze_intent(body: dict):
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
