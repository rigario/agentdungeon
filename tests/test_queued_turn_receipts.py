"""Queued turn receipt/status contract for locked live-tick mode."""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.services.database import init_db, get_db
from app.services.queued_turns import (
    enqueue_turn,
    get_turn_status,
    mark_turn_processing,
    mark_turn_completed,
)


def test_queued_turn_api_returns_202_and_status_url():
    from fastapi.testclient import TestClient
    from app.main import app

    init_db()
    conn = get_db()
    for table in ["queued_turns", "share_tokens", "dm_sessions", "event_log", "doom_clock", "character_fronts", "characters"]:
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    conn.execute(
        """
        INSERT OR REPLACE INTO characters (
            id, player_id, name, race, class, level,
            hp_current, hp_max, ac_value, ability_scores_json, location_id
        ) VALUES ('api-char-1', 'api-player', 'API Hero', 'Human', 'Fighter', 1, 10, 10, 16, '{}', 'rusty-tankard')
        """
    )
    conn.commit()
    conn.close()

    client = TestClient(app)
    resp = client.post(
        "/turns/queue",
        json={
            "character_id": "api-char-1",
            "message": "I wait for the tick.",
            "idempotency_key": "api-key-1",
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] is True
    assert data["status"] == "queued"
    assert data["status_url"].endswith(f"/turns/{data['turn_id']}/status")

    status_resp = client.get(f"/turns/{data['turn_id']}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["turn_id"] == data["turn_id"]


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    conn = get_db()
    for table in ["queued_turns", "share_tokens", "dm_sessions", "event_log", "doom_clock", "character_fronts", "characters"]:
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    conn.execute(
        """
        INSERT OR REPLACE INTO characters (
            id, player_id, name, race, class, level,
            hp_current, hp_max, ac_value, ability_scores_json, location_id
        ) VALUES (?, ?, ?, ?, ?, 1, 10, 10, 16, ?, ?)
        """,
        (
            "receipt-char-1",
            "test-player",
            "Receipt Hero",
            "Human",
            "Fighter",
            json.dumps({"STR": 16, "DEX": 12, "CON": 14, "INT": 10, "WIS": 11, "CHA": 8}),
            "rusty-tankard",
        ),
    )
    conn.execute(
        """
        INSERT INTO share_tokens (id, character_id, token, label, revoked)
        VALUES ('share-1', 'receipt-char-1', 'portal-token-1', 'Test Portal', 0)
        """
    )
    conn.commit()
    conn.close()
    yield


def test_enqueue_turn_returns_accepted_receipt_with_agent_instructions():
    receipt = enqueue_turn(
        character_id="receipt-char-1",
        message="I ask Aldric what happened in the woods.",
        idempotency_key="agent-run-1-turn-1",
        session_id="dm-session-1",
        base_url="https://agentdungeon.com",
    )

    assert receipt["accepted"] is True
    assert receipt["status"] == "queued"
    assert receipt["turn_id"].startswith("turn_")
    assert receipt["character_id"] == "receipt-char-1"
    assert receipt["tick_id"].startswith("tick_")
    assert receipt["next_tick_at"]
    assert receipt["cutoff_at"]
    assert receipt["estimated_processing_window_seconds"] == 120
    assert receipt["status_url"] == f"https://agentdungeon.com/turns/{receipt['turn_id']}/status"
    assert receipt["portal_url"] == "https://agentdungeon.com/portal/portal-token-1/view"
    assert "Turn accepted" in receipt["message"]
    assert any("idempotency_key" in step for step in receipt["instructions"])


def test_enqueue_turn_is_idempotent_for_same_character_and_key():
    first = enqueue_turn(
        character_id="receipt-char-1",
        message="I move north.",
        idempotency_key="same-key",
        base_url="https://agentdungeon.com",
    )
    second = enqueue_turn(
        character_id="receipt-char-1",
        message="I move north again by retry.",
        idempotency_key="same-key",
        base_url="https://agentdungeon.com",
    )

    assert second["turn_id"] == first["turn_id"]
    assert second["duplicate"] is True
    assert second["status"] == "queued"

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM queued_turns WHERE character_id = ?", ("receipt-char-1",)).fetchone()[0]
    conn.close()
    assert count == 1


def test_status_flow_queued_processing_completed_with_result_payload():
    receipt = enqueue_turn(
        character_id="receipt-char-1",
        message="I listen at the door.",
        idempotency_key="flow-key",
        base_url="https://agentdungeon.com",
    )

    queued = get_turn_status(receipt["turn_id"], base_url="https://agentdungeon.com")
    assert queued["status"] == "queued"
    assert queued["result"] is None

    processing = mark_turn_processing(receipt["turn_id"], base_url="https://agentdungeon.com")
    assert processing["status"] == "processing"
    assert "tick is processing" in processing["message"]

    completed = mark_turn_completed(
        receipt["turn_id"],
        result={"narration": {"scene": "You hear rain on stone."}},
        base_url="https://agentdungeon.com",
    )
    assert completed["status"] == "completed"
    assert completed["result"]["narration"]["scene"] == "You hear rain on stone."
    assert "completed" in completed["message"]
