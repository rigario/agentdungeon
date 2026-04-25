"""Regression tests for the actual DM-agent flow contract.

These tests distinguish a real DM narration flow from the false-green
"/dm/turn returns 200 but only passthroughs server narration" state.
"""

import asyncio
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DM_RUNTIME_ROOT = os.path.join(PROJECT_ROOT, "dm-runtime")


def _clear_app_modules():
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name)


def _prefer_dm_runtime_app():
    _clear_app_modules()
    sys.path[:] = [p for p in sys.path if p not in (PROJECT_ROOT, DM_RUNTIME_ROOT)]
    sys.path.insert(0, DM_RUNTIME_ROOT)
    sys.path.insert(1, PROJECT_ROOT)


def _prefer_rules_app():
    _clear_app_modules()
    sys.path[:] = [p for p in sys.path if p not in (PROJECT_ROOT, DM_RUNTIME_ROOT)]
    sys.path.insert(0, PROJECT_ROOT)
    sys.path.insert(1, DM_RUNTIME_ROOT)


def test_dm_profile_defaults_to_hermes_and_kimi_for_coding(monkeypatch):
    """Production DM profile defaults should target the Hermes agent path."""
    _prefer_dm_runtime_app()
    import importlib
    import app.services.dm_profile as dm_profile

    monkeypatch.delenv("DM_HERMES_MODE", raising=False)
    monkeypatch.delenv("DM_NARRATOR_MODEL", raising=False)
    dm_profile = importlib.reload(dm_profile)

    assert dm_profile.DM_HERMES_MODE == "hermes"
    assert dm_profile.DM_NARRATOR_MODEL == "kimi-for-coding"
    assert dm_profile.KIMI_API_KEY == (
        os.environ.get("KIMI_API_KEY", "")
        or os.environ.get("DM_FIRE_PASS_API_KEY", "")
        or os.environ.get("FIRE_PASS_API_KEY", "")
    )


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200
        self.text = "OK"

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _FakeHTTPClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, json):
        self.calls.append((url, json))
        return _FakeResponse({
            "narration": {"scene": "Hermes narrated", "npc_lines": [], "tone": "neutral"},
            "choices": [],
            "session_id": "sess-real",
        })


def test_dm_proxy_uses_narrate_endpoint_not_turn(monkeypatch):
    """Rules-server augmentation must call narrate-only DM endpoint, never /dm/turn."""
    _prefer_rules_app()
    import importlib
    import app.services.dm_proxy as dm_proxy

    dm_proxy = importlib.reload(dm_proxy)
    saved = []
    monkeypatch.setattr(dm_proxy, "save_dm_session", lambda char_id, sid: saved.append((char_id, sid)))

    fake_client = _FakeHTTPClient()
    proxy = dm_proxy.DMProxyClient(base_url="http://dm-runtime:8610", client=fake_client)
    result = asyncio.run(proxy.narrate(
        character_id="char-1",
        world_context={"location": {"id": "rusty-tankard"}},
        resolved_result={"success": True, "narration": "server text"},
        player_message="look around",
        session_id=None,
    ))

    assert fake_client.calls
    url, payload = fake_client.calls[0]
    assert url.endswith("/dm/narrate")
    assert not url.endswith("/dm/turn")
    assert payload["resolved_result"]["narration"] == "server text"
    assert result["session_id"] == "sess-real"
    assert saved == [("char-1", "sess-real")]


def test_dm_turn_does_not_take_runtime_lock():
    """DM /turn orchestrates locked rules calls; taking a second runtime lock deadlocks."""
    _prefer_dm_runtime_app()
    import inspect
    import app.routers.turn as turn

    source = inspect.getsource(turn.dm_turn)
    assert "acquire_character_lock" not in source
    assert "release_character_lock" not in source


def test_rules_client_marks_actions_as_dm_runtime_origin(monkeypatch):
    """DM-runtime calls to rules /actions must not trigger rules-server DM augmentation."""
    _prefer_dm_runtime_app()
    import app.services.rules_client as rules_client

    seen = {}

    class FakeAsyncClient:
        async def post(self, url, json=None, headers=None):
            seen["url"] = url
            seen["json"] = json
            seen["headers"] = headers or {}
            return _FakeResponse({"success": True})

    monkeypatch.setattr(rules_client, "_client", FakeAsyncClient())
    result = asyncio.run(rules_client.submit_action("char-1", {"action_type": "explore"}))

    assert result == {"success": True}
    assert seen["url"] == "/characters/char-1/actions"
    assert seen["headers"]["X-DM-Runtime"] == "1"


def test_passthrough_choices_tolerate_string_connections():
    """World-context connections can be ID strings; synthesis must not crash."""
    _prefer_dm_runtime_app()
    import app.services.synthesis as synthesis

    response = synthesis._build_passthrough(
        {"narration": "You look around.", "events": []},
        {"type": "explore", "details": {}},
        {"connections": ["thornhold", {"id": "south-road", "name": "South Road"}]},
    )

    assert response["choices"][0]["id"] == "thornhold"
    assert response["choices"][0]["label"] == "Go to thornhold"
    assert response["choices"][1]["id"] == "south-road"


def test_combat_events_populate_server_trace_combat_log():
    """Combat events must appear in server_trace.combat_log, not only mechanics."""
    _prefer_dm_runtime_app()
    import app.services.synthesis as synthesis

    response = synthesis._build_passthrough(
        {
            "combat_id": "combat-1",
            "events": [
                {"description": "Goblin hits you for 5 damage!"},
                "You fall before you can act.",
            ],
            "character_state": {"hp": {"current": 0, "max": 12}, "location_id": "forest-edge"},
        },
        {"type": "combat", "details": {}},
        {},
    )

    assert response["server_trace"]["combat_log"] == [
        "Goblin hits you for 5 damage!",
        "You fall before you can act.",
    ]


def test_combat_log_fallback_uses_narration_when_events_empty():
    """Combat log must not be empty: fallback to narration for combat/start with no events."""
    _prefer_dm_runtime_app()
    import app.services.synthesis as synthesis

    # Simulate a combat/start response where player goes first (no pre-combat enemy attacks)
    server_result = {
        "success": True,
        "narration": "Goblin Ambush! Initiative: You (15), Goblin (12). Your turn — what do you do?",
        "events": [],  # No pre-combat events
        "character_state": {"hp": {"current": 12, "max": 12}, "location_id": "forest-edge"},
        "enemies": [{"name": "Goblin 1", "hp": 7, "ac": 15}],
        "round": 1,
        "combat_id": "abc123",
    }
    intent = {"type": "combat", "details": {}}
    world_context = {}

    response = synthesis._build_passthrough(server_result, intent, world_context)

    combat_log = response.get("server_trace", {}).get("combat_log", [])
    assert isinstance(combat_log, list)
    assert len(combat_log) > 0, "combat_log must not be empty for combat start with no events"
    # The fallback should have used the narration as the combat log entry
    assert "Goblin Ambush" in combat_log[0]


def test_synthesize_narration_llm_path_returns_server_trace():
    """synthesize_narration must include server_trace when using LLM narrator path."""
    _prefer_dm_runtime_app()
    import importlib
    import app.services.synthesis as synthesis
    import app.services.narrator as narrator

    # Build minimal server_result
    server_result = {
        "success": True,
        "narration": "You explore the forest.",
        "events": [{"desc": "You find a path."}],
        "character_state": {"hp": {"current": 10, "max": 12}},
    }
    intent = {"type": "explore", "details": {}}
    world_context = {"connections": [{"id": "path", "name": "Forest Path"}]}

    # --- Case 1: LLM narrator succeeds ---
    fake_llm = {
        "scene": "The forest is quiet.",
        "npc_lines": [],
        "tone": "neutral",
    }

    original_narrate = narrator.narrate

    async def fake_narrate(*args, **kwargs):
        return fake_llm

    # Temporarily replace narrator.narrate
    import types
    saved = narrator.narrate
    narrator.narrate = fake_narrate

    try:
        # Need to reload synthesis to pick up any module-level changes? No, just call
        result = asyncio.run(
            synthesis.synthesize_narration(server_result, intent, world_context, session_id="sess-123")
        )

        assert "server_trace" in result, "synthesize_narration response missing server_trace key"
        st = result["server_trace"]
        assert isinstance(st, dict), "server_trace must be a dict"
        assert "turn_id" in st
        assert "combat_log" in st
        # LLM path should still include server trace
        assert st.get("raw_server_response_keys")  # should populate keys from server_result
    finally:
        narrator.narrate = saved


def test_synthesize_narration_passthrough_path_returns_server_trace():
    """synthesize_narration must include server_trace when falling back to passthrough."""
    _prefer_dm_runtime_app()
    import importlib
    import app.services.synthesis as synthesis
    import app.services.narrator as narrator

    server_result = {
        "success": True,
        "narration": "Server narrates directly.",
        "events": [{"desc": "Event from server"}],
        "character_state": {"hp": {"current": 10, "max": 12}},
    }
    intent = {"type": "explore", "details": {}}
    world_context = {"connections": [{"id": "clear", "name": "Clearing"}]}

    # --- Case 2: LLM narrator unavailable / empty output -> passthrough ---
    async def fake_narrate_none(*args, **kwargs):
        return None

    saved = narrator.narrate
    narrator.narrate = fake_narrate_none

    try:
        result = asyncio.run(
            synthesis.synthesize_narration(server_result, intent, world_context)
        )

        assert "server_trace" in result, "synthesize_narration passthrough response missing server_trace key"
        st = result["server_trace"]
        assert isinstance(st, dict)
        assert "turn_id" in st
        assert "combat_log" in st
        # server_endpoint_called may be empty string (filled by caller), but present
        assert "raw_server_response_keys" in st
    finally:
        narrator.narrate = saved


def test_extract_trace_returns_expected_schema():
    """_extract_trace must return a well-formed dict (regression: was missing causing NameError)."""
    _prefer_dm_runtime_app()
    import app.services.synthesis as synthesis

    server_result = {
        "turn_id": "turn-abc123",
        "decision_point": "explore",
        "available_actions": ["explore", "rest"],
        "events": [{"desc": "Encounter"}],
        # combat_log fill-in is tested separately in test_dm_runtime_synthesis.py
    }

    trace = synthesis._extract_trace(server_result)

    assert trace["turn_id"] == "turn-abc123"
    assert trace["decision_point"] == "explore"
    assert trace["available_actions"] == ["explore", "rest"]
    # Combat events from `events` get extracted via _get_combat_events
    assert isinstance(trace["combat_log"], list)
    assert len(trace["combat_log"]) > 0  # at least one event stringified
    # intent_used and server_endpoint_called are filled by caller — they can be None/empty
    assert "intent_used" in trace
    assert "server_endpoint_called" in trace
    assert trace["raw_server_response_keys"] == list(server_result.keys())




def test_hermes_session_id_is_extracted_from_stdout_or_stderr():
    """Hermes CLI may print session_id on stdout or stderr; keep it before JSON filtering."""
    _prefer_dm_runtime_app()
    import app.services.dm_profile as dm_profile

    assert dm_profile._extract_hermes_session_id('session_id: abc123\n{"scene":"ok"}', '') == 'abc123'
    assert dm_profile._extract_hermes_session_id('{"scene":"ok"}', 'session_id: def456\n') == 'def456'


def test_actions_explore_result_is_not_classified_as_combat_from_plain_events():
    """A non-combat action with events must not get combat choices just because events exist."""
    _prefer_dm_runtime_app()
    import asyncio
    import app.services.synthesis as synthesis
    from app.services.intent_router import Intent, IntentRouter, IntentType, ServerEndpoint

    class FakeRulesClient:
        async def submit_action(self, character_id, payload):
            return {
                'success': True,
                'narration': 'You find a local map.',
                'events': [{'type': 'loot', 'description': 'You find a local map.'}],
                'character_state': {'hp': {'current': 12, 'max': 12}, 'location_id': 'rusty-tankard'},
            }

    intent = Intent(
        type=IntentType.EXPLORE,
        action_type='explore',
        details={'action_type': 'explore'},
    )
    result = asyncio.run(IntentRouter(FakeRulesClient())._route_action('char-1', intent))
    payload = result.to_dict()

    assert 'combat_log' not in payload
    assert 'combat_over' not in payload
    assert synthesis._is_combat_response(payload) is False
    choices = synthesis._extract_choices(payload, {'connections': [{'id': 'south-road', 'name': 'South Road'}]})
    assert choices
    assert choices[0]['id'] == 'south-road'
    assert not any(choice['id'] == 'attack' for choice in choices)
