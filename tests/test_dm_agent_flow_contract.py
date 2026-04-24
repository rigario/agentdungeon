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
