"""Agent session reliability: replay, idempotent submission, tenancy, redaction.

These pin what the web workspace relies on when a connection drops: a resend of
the same turn never starts (or charges) a second run, the durable transcript is
owner-scoped and cursor-ordered, a deleted conversation stays deleted, and the
timeline a reconnecting client draws carries server times and never echoes a
credential the model put into tool arguments.
"""
from __future__ import annotations

from apps.api.services.agent_service import (
    EPHEMERAL_STREAM_EVENTS,
    _parse_sse,
    _sse,
    redact_tool_arguments,
    with_run_events,
)
from datetime import timedelta

from apps.api.services import agent_service
from packages.database.models import AgentConversation, AgentMessage, AgentRun, AgentRunEvent, AgentToolCall, utcnow
from tests.conftest import auth_headers


def _conversation(api_client, user) -> str:
    response = api_client.post("/api/agent/conversations", json={}, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["id"]


def test_a_resent_turn_reattaches_instead_of_starting_a_second_run(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    url = f"/api/agent/conversations/{conversation_id}/messages"
    body = {"content": "What moved BTC today?", "research_mode": False, "client_request_id": "send-0001-abcdef"}

    first = api_client.post(url, json=body, headers=auth_headers(normal_user))
    assert first.status_code == 200, first.text
    runs = db.query(AgentRun).filter_by(conversation_id=conversation_id).all()
    assert len(runs) == 1

    again = api_client.post(url, json=body, headers=auth_headers(normal_user))
    assert again.status_code == 409, again.text
    detail = again.json()["detail"]
    assert detail["code"] == "DUPLICATE_SUBMISSION"
    assert detail["runId"] == runs[0].id
    assert detail["messageId"] == runs[0].assistant_message_id
    db.expire_all()
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 1
    assert db.query(AgentMessage).filter_by(conversation_id=conversation_id, role="user").count() == 1

    # A different attempt id is a genuinely new question.
    fresh = api_client.post(url, json={**body, "client_request_id": "send-0002-abcdef"}, headers=auth_headers(normal_user))
    assert fresh.status_code == 200, fresh.text
    db.expire_all()
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 2


def test_a_resend_that_lands_while_the_first_attempt_commits_is_still_a_duplicate(api_client, db, normal_user, monkeypatch):
    # Stale-run recovery commits. It used to run after the duplicate check,
    # which released the conversation lock: a resend arriving in that window
    # passed the check too and started (and charged) a second run.
    conversation_id = _conversation(api_client, normal_user)
    key = "send-race-abcdef"
    original = agent_service.recover_stale_runs

    def first_attempt_commits_meanwhile(session):
        session.add(AgentMessage(conversation_id=conversation_id, user_id=normal_user.id, role="user", content="q",
                                 status="completed", context_json={"client_request_id": key}))
        session.commit()
        return original(session)

    monkeypatch.setattr(agent_service, "recover_stale_runs", first_attempt_commits_meanwhile)
    resent = api_client.post(f"/api/agent/conversations/{conversation_id}/messages",
                             json={"content": "q", "research_mode": False, "client_request_id": key}, headers=auth_headers(normal_user))
    assert resent.status_code == 409, resent.text
    db.expire_all()
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0
    assert db.query(AgentMessage).filter_by(conversation_id=conversation_id, role="user").count() == 1


def test_regenerate_is_idempotent_and_a_deleted_conversation_is_not_found(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    sent = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "What moved BTC today?", "research_mode": False}, headers=headers)
    assert sent.status_code == 200, sent.text
    assistant = db.query(AgentMessage).filter_by(conversation_id=conversation_id, role="assistant").one()
    url = f"/api/agent/messages/{assistant.id}/regenerate"
    body = {"content": "", "research_mode": False, "client_request_id": "regen-0001-abcdef"}

    assert api_client.post(url, json=body, headers=headers).status_code == 200
    again = api_client.post(url, json=body, headers=headers)
    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "DUPLICATE_SUBMISSION"
    db.expire_all()
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 2

    assert api_client.delete(f"/api/agent/conversations/{conversation_id}", headers=headers).status_code == 200
    # Was an unhandled LookupError (HTTP 500).
    assert api_client.post(url, json={"content": "", "research_mode": False}, headers=headers).status_code == 404


def test_the_submission_key_is_scoped_to_its_conversation(api_client, db, normal_user):
    body = {"content": "same words", "research_mode": False, "client_request_id": "send-shared-123456"}
    for conversation_id in (_conversation(api_client, normal_user), _conversation(api_client, normal_user)):
        response = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json=body, headers=auth_headers(normal_user))
        assert response.status_code == 200, response.text


def test_a_malformed_submission_key_is_rejected_before_any_run(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    response = api_client.post(
        f"/api/agent/conversations/{conversation_id}/messages",
        json={"content": "hi", "client_request_id": "bad key with spaces"},
        headers=auth_headers(normal_user),
    )
    assert response.status_code == 422
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0


def test_a_deleted_conversation_cannot_be_read_or_continued(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    assert api_client.delete(f"/api/agent/conversations/{conversation_id}", headers=headers).status_code == 200

    assert api_client.get(f"/api/agent/conversations/{conversation_id}", headers=headers).status_code == 404
    assert api_client.get(f"/api/agent/conversations/{conversation_id}/messages", headers=headers).status_code == 404
    posted = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "still there?"}, headers=headers)
    assert posted.status_code == 404
    assert api_client.patch(f"/api/agent/conversations/{conversation_id}", json={"archived": False}, headers=headers).status_code == 404
    db.expire_all()
    assert db.get(AgentConversation, conversation_id).status == "deleted"
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0


def test_another_users_conversation_and_messages_are_not_found(api_client, normal_user, max_user):
    conversation_id = _conversation(api_client, normal_user)
    other = auth_headers(max_user)
    assert api_client.get(f"/api/agent/conversations/{conversation_id}", headers=other).status_code == 404
    # Was an unhandled LookupError (HTTP 500) before; an id must not be probeable.
    assert api_client.get(f"/api/agent/conversations/{conversation_id}/messages", headers=other).status_code == 404
    assert api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json={"content": "x"}, headers=other).status_code == 404


def test_archive_round_trip_keeps_the_conversation_listed_and_readable(api_client, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    archived = api_client.patch(f"/api/agent/conversations/{conversation_id}", json={"archived": True}, headers=headers)
    assert archived.status_code == 200
    assert archived.json()["conversation"]["archived_at"]
    listed = {row["id"]: row for row in api_client.get("/api/agent/conversations", headers=headers).json()["conversations"]}
    assert listed[conversation_id]["archived_at"]
    assert api_client.get(f"/api/agent/conversations/{conversation_id}", headers=headers).status_code == 200
    restored = api_client.patch(f"/api/agent/conversations/{conversation_id}", json={"archived": False}, headers=headers)
    assert restored.json()["conversation"]["archived_at"] is None


def _seed_run_with_events(db, user, events: list[tuple[int, str, dict]], status: str = "running") -> AgentRun:
    conversation = AgentConversation(user_id=user.id, title="replay")
    db.add(conversation); db.flush()
    question = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="user", content="q", status="completed")
    answer = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="assistant", content="", status="streaming")
    db.add_all([question, answer]); db.flush()
    run = AgentRun(conversation_id=conversation.id, user_id=user.id, user_message_id=question.id,
                   assistant_message_id=answer.id, model="mock-model", trace_id="replay", status=status)
    db.add(run); db.flush()
    for seq, kind, data in events:
        db.add(AgentRunEvent(run_id=run.id, seq=seq, type=kind, data_json={**data, "seq": seq}))
    db.commit()
    return run


def test_replay_returns_only_events_after_the_cursor_in_order(api_client, db, normal_user):
    run = _seed_run_with_events(db, normal_user, [
        (3, "tool.completed", {"toolCallId": "c1"}),
        (1, "run.started", {"runId": "r"}),
        (2, "tool.started", {"toolCallId": "c1"}),
    ])
    headers = auth_headers(normal_user)
    page = api_client.get(f"/api/agent/runs/{run.id}/events?after=1", headers=headers).json()
    assert [event["seq"] for event in page["events"]] == [2, 3]
    assert page["lastSeq"] == 3 and page["status"] == "running" and page["truncated"] is False
    assert page["messageId"] == run.assistant_message_id

    tail = api_client.get(f"/api/agent/runs/{run.id}/events?after=3", headers=headers).json()
    assert tail["events"] == [] and tail["lastSeq"] == 3
    # A negative cursor is clamped rather than leaking rows below zero.
    assert len(api_client.get(f"/api/agent/runs/{run.id}/events?after=-5", headers=headers).json()["events"]) == 3


def test_replay_and_cancel_are_owner_scoped(api_client, db, normal_user, max_user):
    run = _seed_run_with_events(db, normal_user, [(1, "run.started", {"runId": "r"})])
    other = auth_headers(max_user)
    assert api_client.get(f"/api/agent/runs/{run.id}/events", headers=other).status_code == 404
    assert api_client.post(f"/api/agent/runs/{run.id}/cancel", headers=other).status_code == 404
    db.expire_all()
    assert db.get(AgentRun, run.id).status == "running"


def test_cancel_is_idempotent_and_never_reopens_a_finished_run(api_client, db, normal_user):
    run = _seed_run_with_events(db, normal_user, [], status="running")
    headers = auth_headers(normal_user)
    assert api_client.post(f"/api/agent/runs/{run.id}/cancel", headers=headers).json()["status"] == "canceled"
    assert api_client.post(f"/api/agent/runs/{run.id}/cancel", headers=headers).json()["status"] == "canceled"
    finished = _seed_run_with_events(db, normal_user, [], status="completed")
    assert api_client.post(f"/api/agent/runs/{finished.id}/cancel", headers=headers).json()["status"] == "completed"


class _Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[str, int, str, dict]] = []

    def __call__(self, run_id: str, seq: int, event: str, data: dict) -> None:
        self.rows.append((run_id, seq, event, data))


def test_every_frame_carries_server_time_and_heartbeats_are_not_stored():
    recorder = _Recorder()
    frames = [
        _sse("approval.required", {"toolCallId": "c1", "expiresAt": "2026-10-28T00:02:00+00:00"}),
        _sse("approval.waiting", {"toolCallId": "c1"}),
        _sse("approval.waiting", {"toolCallId": "c1"}),
        _sse("tool.completed", {"toolCallId": "c1", "at": "2026-10-28T00:00:05+00:00"}),
    ]
    out = [_parse_sse(frame)[1] for frame in with_run_events(iter(frames), "r1", persist=recorder)]
    assert all(isinstance(item["at"], str) and item["at"] for item in out)
    # A time the producer already stamped is preserved, not overwritten.
    assert out[-1]["at"] == "2026-10-28T00:00:05+00:00"
    assert "approval.waiting" in EPHEMERAL_STREAM_EVENTS
    assert [row[2] for row in recorder.rows] == ["approval.required", "tool.completed"]


def test_tool_arguments_shown_in_the_timeline_are_redacted():
    shown = redact_tool_arguments({
        "symbol": "BTC",
        "api_key": "sk-live-123",
        "nested": {"Authorization": "Bearer abc", "accountNumber": "123456789", "depth": 3},
        "rows": [{"password": "hunter2", "note": "x" * 600}],
    })
    assert shown["symbol"] == "BTC"
    assert shown["api_key"] == "••••"
    assert shown["nested"]["Authorization"] == "••••"
    assert shown["nested"]["accountNumber"] == "••••"
    assert shown["nested"]["depth"] == 3
    assert shown["rows"][0]["password"] == "••••"
    assert len(shown["rows"][0]["note"]) <= 501
    assert "sk-live-123" not in repr(shown) and "hunter2" not in repr(shown)


def test_a_reloaded_conversation_shows_pending_approval_inputs_redacted(api_client, db, normal_user):
    # The live stream already masks these; a page reload must not show the raw copy.
    run = _seed_run_with_events(db, normal_user, [], status="running")
    db.add(AgentToolCall(run_id=run.id, tool_name="broker.connect", status="awaiting_approval",
                         arguments_json={"exchange": "binance", "api_key": "sk-live-123"},
                         approval_expires_at=utcnow() + timedelta(minutes=5)))
    db.commit()
    shown = api_client.get(f"/api/agent/conversations/{run.conversation_id}", headers=auth_headers(normal_user)).json()
    [pending] = shown["pending_approvals"]
    assert pending["arguments"] == {"exchange": "binance", "api_key": "••••"}
    assert "sk-live-123" not in repr(shown)
