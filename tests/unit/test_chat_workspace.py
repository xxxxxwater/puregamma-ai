from datetime import timedelta
import io
import json
import os
import threading
import time
import pytest
from PIL import Image
from tests.conftest import auth_headers
from apps.api.services.agent_service import stream_run
from apps.api.services.chat_workspace import prepare_file, resolve_attachments, tool_permission
from packages.database.models import AgentAttachmentRecord, AgentConversation, AgentMessage, AgentRun, AgentToolCall, utcnow


def test_upload_download_and_tenant_isolation(api_client, db, normal_user, max_user):
    headers = auth_headers(normal_user)
    assert api_client.get("/api/agent/workspace-capabilities").status_code == 401
    response = api_client.post("/api/agent/attachments?name=notes.txt", content=b"durable user notes", headers=headers)
    assert response.status_code == 200, response.text
    item = response.json()["attachment"]
    assert item["content"] == ""
    assert api_client.get(item["url"], headers=headers).content == b"durable user notes"
    assert api_client.get(item["url"], headers=auth_headers(max_user)).status_code == 404
    resolved = resolve_attachments(db, normal_user.id, [{"id": item["id"], "content": "forged", "name": "forged"}])
    assert resolved[0]["content"] == "durable user notes"
    with pytest.raises(LookupError):
        resolve_attachments(db, max_user.id, [item])
    row = db.get(AgentAttachmentRecord, item["id"])
    row.payload = b"corrupted"
    db.commit()
    assert api_client.get(item["url"], headers=headers).status_code == 409


def test_file_validation_and_image_normalization():
    with pytest.raises(ValueError):
        prepare_file("run.exe", b"malware")
    with pytest.raises(ValueError):
        prepare_file("long.txt", b"x" * 50001)
    with pytest.raises(ValueError):
        prepare_file("empty.pdf", b"")
    image = Image.new("RGB", (2500, 1000), "red")
    output = io.BytesIO()
    image.save(output, format="PNG")
    kind, mime, text, payload = prepare_file("photo.png", output.getvalue())
    assert (kind, mime, text) == ("image", "image/jpeg", "")
    assert Image.open(io.BytesIO(payload)).width == 2048


@pytest.mark.parametrize("mode,unknown,stateful", [
    ("read-only", "deny", "deny"),
    ("workspace-write", "deny", "ask"),
    ("full-access", "allow", "allow"),
])
def test_permissions_fail_closed_for_unknown_tools(mode, unknown, stateful, monkeypatch):
    import apps.api.services.chat_workspace as workspace
    monkeypatch.setattr(workspace, "STATEFUL_TOOLS", frozenset({"write_action"}))
    assert tool_permission(mode, "get_market_quote") == "allow"
    # A tool nobody classified must never reach the user as a confirmation card
    # they would learn to approve; only a reviewed stateful tool earns the ask.
    assert tool_permission(mode, "future_mutating_tool") == unknown
    assert tool_permission(mode, "write_action") == stateful


def test_persisted_permission_and_explicit_full_access(api_client, normal_user, max_user):
    h = auth_headers(normal_user)
    item = api_client.post("/api/agent/conversations", json={}, headers=h).json()["conversation"]
    url = "/api/agent/conversations/" + item["id"]
    assert item["permission_mode"] == "workspace-write"
    assert api_client.patch(url, json={"permission_mode": "full-access"}, headers=h).status_code == 400
    assert api_client.patch(url, json={"permission_mode": "full-access", "acknowledge_full_access": True}, headers=h).status_code == 200
    assert api_client.get(url, headers=h).json()["conversation"]["permission_mode"] == "full-access"
    assert api_client.patch(url, json={"permission_mode": "read-only"}, headers=auth_headers(max_user)).status_code == 404


def test_approval_tenant_expiry_and_replay(api_client, db, normal_user, max_user):
    conversation = AgentConversation(user_id=normal_user.id, title="approval")
    db.add(conversation); db.flush()
    messages = [AgentMessage(conversation_id=conversation.id, user_id=normal_user.id, role=r, content="test", status="completed") for r in ("user", "assistant")]
    db.add_all(messages); db.flush()
    run = AgentRun(conversation_id=conversation.id, user_id=normal_user.id, user_message_id=messages[0].id, assistant_message_id=messages[1].id, model="deepseek-flash", trace_id="test-approval", status="running")
    db.add(run); db.flush()
    call = AgentToolCall(run_id=run.id, tool_name="write_action", status="awaiting_approval", approval_expires_at=utcnow()+timedelta(seconds=120))
    db.add(call); db.commit()
    url = f"/api/agent/tool-calls/{call.id}/approval"
    assert api_client.post(url, json={"decision":"approved"}, headers=auth_headers(max_user)).status_code == 404
    assert api_client.post(url, json={"decision":"approved"}, headers=auth_headers(normal_user)).status_code == 200
    assert api_client.post(url, json={"decision":"approved"}, headers=auth_headers(normal_user)).status_code == 409
    call.approval = None; call.approval_expires_at = utcnow()-timedelta(seconds=1); db.commit()
    assert api_client.post(url, json={"decision":"approved"}, headers=auth_headers(normal_user)).status_code == 409


def _events(lines) -> list[dict]:
    """Parse the SSE frames the stream emits: 'event: <name>\\ndata: <json>'."""
    out = []
    for line in lines:
        name, _, payload = line.partition("\n")
        if not payload.startswith("data: "):
            continue
        out.append({"event": name.removeprefix("event: "), "data": json.loads(payload[len("data: "):])})
    return out


def _collect(stream, into: list[dict]) -> None:
    """Drain a stream frame by frame so a caller polling `into` sees each event
    as it is produced. `list.extend(_events(...))` would publish nothing until
    the generator finished, which is the opposite of what a blocking-run test
    needs to observe."""
    for line in stream:
        name, _, payload = line.partition("\n")
        if payload.startswith("data: "):
            into.append({"event": name.removeprefix("event: "), "data": json.loads(payload[len("data: "):])})


def _seed_stream_run(db, user, message: str, deadline_seconds: int = 30) -> tuple[AgentRun, callable]:
    conversation = AgentConversation(user_id=user.id, title="stream")
    db.add(conversation); db.flush()
    user_message = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="user", content=message,
                                status="completed",
                                context_json={"research_mode": True, "data_sources": [], "skills": [],
                                              "custom_prompt": "", "attachments": [],
                                              "permission_mode": "workspace-write",
                                              "runtime": {"intent": "general_research", "assets": ["BTC"]}})
    assistant = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="assistant", content="",
                             status="streaming")
    db.add_all([user_message, assistant]); db.flush()
    run = AgentRun(conversation_id=conversation.id, user_id=user.id, user_message_id=user_message.id,
                   assistant_message_id=assistant.id, model="mock-model", trace_id="test-stream",
                   status="pending")
    db.add(run); db.commit()
    return run


def test_streaming_run_completes_without_an_unclassified_tool_denial(db, normal_user):
    """A plain question must not be answered with a permission refusal.

    `tool_permission` denies anything it has not classified, so a tool the
    research plan schedules but the allowlist forgot fails the turn closed. This
    runs the real generator end to end and asserts no tool was denied.
    """
    os.environ["ENABLE_MOCK_AGENT"] = "true"
    run = _seed_stream_run(db, normal_user, "what is the latest on BTC")
    events = _events(stream_run(db, normal_user, run.id, "en"))
    denied = [item for item in events if item["data"].get("error") == "READ_ONLY_PERMISSION"]
    assert not denied, f"an unclassified tool was denied: {denied}"
    assert any(item["event"] == "run.failed" and item["data"].get("code") != "MODEL_NOT_CONFIGURED" for item in events) is False, events
    assert any(item["event"] == "tool.completed" for item in events), [item["event"] for item in events]


def test_streaming_run_waits_for_approval_then_resumes(api_client, db, normal_user):
    """The confirming half of the permission contract, with the real generator.

    The stream is consumed on a worker thread while the approval arrives over
    HTTP from the main thread — the ordering production produces. `write_action`
    is not a real tool: the test classifies it as stateful, so the prompt path is
    exercised without depending on a mutating tool existing in the registry.
    """
    import apps.api.services.chat_workspace as workspace
    os.environ["ENABLE_MOCK_AGENT"] = "true"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(workspace, "STATEFUL_TOOLS", frozenset({"write_action"}))
    try:
        run = _seed_stream_run(db, normal_user, "write_action please")
        from packages.agents.chat.tools import AgentToolRegistry
        monkeypatch.setattr(AgentToolRegistry, "plan", lambda self, *a, **k: [("write_action", {"x": 1})])

        events: list[dict] = []
        failure: list[BaseException] = []
        finished = threading.Event()

        def consume() -> None:
            try:
                _collect(stream_run(db, normal_user, run.id, "en"), events)
            except BaseException as exc:  # noqa: BLE001 - surfaced below
                failure.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=consume, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                ask = next((item for item in events if item["event"] == "approval.required"), None)
                if ask:
                    break
                assert not finished.is_set(), f"stream ended without asking; failure={failure}; events={events}"
                time.sleep(0.05)
            else:
                pytest.fail(f"no approval.required within 30s: {events}")

            call_id = ask["data"]["toolCallId"]
            decision = api_client.post(f"/api/agent/tool-calls/{call_id}/approval",
                                       json={"decision": "approved"}, headers=auth_headers(normal_user))
            assert decision.status_code == 200, decision.text
            assert finished.wait(30), f"run did not resume after approval: {events}"
        finally:
            worker.join(timeout=5)
    finally:
        monkeypatch.undo()

    assert not failure, failure
    order = [item["event"] for item in events if item["data"].get("toolCallId") == call_id]
    assert order.index("tool.started") > order.index("approval.required"), order
    assert order.index("tool.completed") > order.index("tool.started"), order
    assert db.get(AgentToolCall, call_id).approval == "approved"
