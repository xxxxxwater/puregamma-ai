"""HTTP contract the iOS and Android clients are built against.

Every test drives the real FastAPI routes and pins one piece of
docs/mobile/MOBILE_API_CONTRACT.md §8: status code, error code and JSON shape.
The responses are also the shared sample files in ``docs/mobile/fixtures``
that both mobile unit-test suites decode, so a server change that would break
a client fails here first instead of in a release build.

Fixtures hold real responses with run-to-run noise normalised (ids, clock
times, latencies). ``PG_WRITE_MOBILE_FIXTURES=1`` rewrites them; otherwise a
fixture that differs from the live response is contract drift and fails.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.config import Settings
from apps.api.services import agent_service
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.database.models import (
    AgentConversation,
    AgentMessage,
    AgentRun,
    AgentRunEvent,
    AgentToolCall,
    NavSnapshot,
    TradingAccount,
    utcnow,
)
from tests.conftest import auth_headers

FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "mobile" / "fixtures"
WRITE = os.environ.get("PG_WRITE_MOBILE_FIXTURES") == "1"

CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")
DECIMAL_TEXT = re.compile(r"^-?\d+(\.\d+)?$")
TERMINAL_RUN_STATUSES = {"completed", "failed", "canceled", "interrupted"}

_UUID_ANYWHERE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")
#: Values that change between runs without changing the contract.
_VOLATILE_NUMBERS = {"latencyMs", "latency_ms"}


class _Normaliser:
    """Replace run-specific ids and times with stable stand-ins.

    The same real value always maps to the same stand-in within one fixture,
    so cross references (a frame's ``runId`` equal to the 409's ``runId``)
    survive normalisation.
    """

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.times: dict[str, str] = {}

    def _id(self, value: str) -> str:
        if value not in self.ids:
            self.ids[value] = f"00000000-0000-4000-8000-{len(self.ids) + 1:012d}"
        return self.ids[value]

    def _time(self, value: str) -> str:
        if value not in self.times:
            moment = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc) + timedelta(seconds=len(self.times))
            fractional = "." in value
            text = moment.isoformat(timespec="microseconds" if fractional else "seconds")
            if value.endswith("Z"):
                text = text.replace("+00:00", "Z")
            elif not re.search(r"[+-]\d{2}:\d{2}$", value):
                text = text.replace("+00:00", "")
            self.times[value] = text
        return self.times[value]

    def __call__(self, value, key: str | None = None):
        if isinstance(value, dict):
            return {name: self(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [self(item, key) for item in value]
        if key in _VOLATILE_NUMBERS and isinstance(value, (int, float)):
            return 12
        if isinstance(value, str):
            if _ISO.match(value):
                return self._time(value)
            # Ids appear on their own and inside paths and messages.
            return _UUID_ANYWHERE.sub(lambda match: self._id(match.group(0)), value)
        return value


def _check_fixture(name: str, payload) -> None:
    """Compare ``payload`` with the committed fixture (or rewrite it)."""
    path = FIXTURES / name
    if name.endswith(".sse"):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if WRITE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"missing fixture {path}; run with PG_WRITE_MOBILE_FIXTURES=1"
    assert path.read_text(encoding="utf-8") == text, f"{name} drifted from the live response; review the contract change and regenerate"


def _http_fixture(name: str, method: str, path: str, response, normalise: _Normaliser | None = None) -> dict:
    normalise = normalise or _Normaliser()
    body = normalise(response.json())
    _check_fixture(name, {"request": {"method": method, "path": normalise(path)}, "status": response.status_code, "body": body})
    return body


def _sse_frames(text: str) -> list[tuple[str, dict]]:
    frames = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        event = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        frames.append((event, json.loads(data)))
    return frames


def _normalised_sse(frames: list[tuple[str, dict]], normalise: _Normaliser) -> str:
    return "".join(f"event: {event}\ndata: {json.dumps(normalise(data), ensure_ascii=False, sort_keys=True)}\n\n" for event, data in frames)


def _conversation(api_client, user) -> str:
    response = api_client.post("/api/agent/conversations", json={}, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["id"]


@pytest.fixture()
def mock_agent(monkeypatch):
    """A deterministic Agent that finishes a turn without any provider key."""
    settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="mock-model")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: MockLLMProvider())
    return settings


def _seed_run(db, user, *, status: str, events: list[tuple[int, str, dict]], conversation: AgentConversation | None = None) -> AgentRun:
    if conversation is None:
        conversation = AgentConversation(user_id=user.id, title="contract")
        db.add(conversation)
        db.flush()
    question = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="user", content="What moved BTC today?", status="completed")
    answer_status = {"running": "streaming", "pending": "streaming"}.get(status, status)
    answer = AgentMessage(conversation_id=conversation.id, user_id=user.id, role="assistant", content="", status=answer_status)
    db.add_all([question, answer])
    db.flush()
    run = AgentRun(conversation_id=conversation.id, user_id=user.id, user_message_id=question.id,
                   assistant_message_id=answer.id, model="mock-model", trace_id="contract", status=status)
    db.add(run)
    db.flush()
    for seq, kind, data in events:
        db.add(AgentRunEvent(run_id=run.id, seq=seq, type=kind,
                             data_json={**data, "seq": seq, "at": f"2026-10-29T08:00:{seq:02d}.000000+00:00"}))
    db.commit()
    return run


# ---------------------------------------------------------------------------
# (a) idempotent send
# ---------------------------------------------------------------------------


def test_a_completed_turn_streams_sequenced_frames(api_client, db, normal_user, mock_agent):
    conversation_id = _conversation(api_client, normal_user)
    body = {"content": "What is the BTC market price?", "locale": "en", "client_request_id": "ios-contract-0001"}
    assert CLIENT_REQUEST_ID.match(body["client_request_id"])

    response = api_client.post(f"/api/agent/conversations/{conversation_id}/messages", json=body, headers=auth_headers(normal_user))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    names = [name for name, _ in frames]
    assert names[0] == "run.started" and names[-1] == "message.completed"
    # Every frame carries a strictly increasing per-run seq and a server time.
    seqs = [data["seq"] for _, data in frames]
    assert seqs == list(range(1, len(frames) + 1))
    assert all(isinstance(data["at"], str) and data["at"] for _, data in frames)
    run_id = frames[0][1]["runId"]
    assert frames[-1][1]["runId"] == run_id and frames[-1][1]["messageId"] == frames[0][1]["messageId"]
    # Frames a mobile client did not know about in 1.5.0 do occur.
    assert {"plan.ready", "evidence.ready"} <= set(names)

    _check_fixture("agent_send_stream_completed.sse", _normalised_sse(frames, _Normaliser()))


def test_a_resend_with_the_same_request_id_is_409_with_the_original_run(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    path = f"/api/agent/conversations/{conversation_id}/messages"
    body = {"content": "What moved BTC today?", "research_mode": False, "client_request_id": "android-contract-0001"}
    assert api_client.post(path, json=body, headers=auth_headers(normal_user)).status_code == 200
    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()

    again = api_client.post(path, json=body, headers=auth_headers(normal_user))

    assert again.status_code == 409
    detail = again.json()["detail"]
    assert set(detail) == {"code", "runId", "status", "messageId", "userMessageId"}
    assert detail["code"] == "DUPLICATE_SUBMISSION"
    assert detail["runId"] == run.id and detail["messageId"] == run.assistant_message_id
    assert detail["userMessageId"] == run.user_message_id
    assert detail["status"] in TERMINAL_RUN_STATUSES | {"pending", "running"}
    db.expire_all()
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 1
    _http_fixture("agent_send_duplicate_409.json", "POST", path, again)


@pytest.mark.parametrize("bad", ["short", "has spaces in it", "x" * 81, "emoji-☃-12345"])
def test_a_malformed_request_id_is_422_before_any_run(api_client, db, normal_user, bad):
    conversation_id = _conversation(api_client, normal_user)
    response = api_client.post(f"/api/agent/conversations/{conversation_id}/messages",
                               json={"content": "hi", "client_request_id": bad}, headers=auth_headers(normal_user))
    assert response.status_code == 422
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0


def test_send_limit_errors_are_429_with_a_code(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    path = f"/api/agent/conversations/{conversation_id}/messages"
    # Fill the user's concurrency slots with runs that are still going.
    for _ in range(agent_service.quota_state(db, normal_user)["concurrent_limit"]):
        _seed_run(db, normal_user, status="running", events=[])

    response = api_client.post(path, json={"content": "hi", "client_request_id": "ios-limit-00001"}, headers=auth_headers(normal_user))

    assert response.status_code == 429
    assert response.json()["detail"]["code"] in {"AGENT_DAILY_LIMIT_REACHED", "AGENT_CONCURRENT_LIMIT_REACHED", "AGENT_GLOBAL_CAPACITY_REACHED"}
    _http_fixture("agent_send_limit_429.json", "POST", path, response)


def test_insufficient_credits_is_402(api_client, db, user_factory):
    broke = user_factory("broke-user@puregamma.ai", plan="Free", credit_balance=0)
    conversation_id = _conversation(api_client, broke)
    path = f"/api/agent/conversations/{conversation_id}/messages"

    response = api_client.post(path, json={"content": "What moved BTC today?", "client_request_id": "ios-credit-00001"}, headers=auth_headers(broke))

    assert response.status_code == 402
    assert response.json() == {"detail": {"code": "INSUFFICIENT_CREDITS"}}
    _http_fixture("agent_send_insufficient_credits_402.json", "POST", path, response)


def _pricing_settings(**overrides) -> Settings:
    values = {
        "openai_api_key": "server-side-test-key",
        "openai_luna_enabled": True,
        "openai_agent_models": (("gpt-5.6-luna", "GPT-5.6 Luna"), ("gpt-6-sol", "GPT-6 Sol")),
        "openai_luna_allowed_plans": ("Max", "Enterprise"),
        "agent_model": "existing-default-model",
        "agent_model_credit_rates": "gpt-5.6-luna=2/1/4",
        "llm_provider": "mock",
        "enable_mock_agent": True,
        "gateway_typesafe_api_key": "",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("name", "model", "plan_user", "overrides", "status", "code"),
    [
        ("agent_send_model_invalid_400.json", "no-such-model", "max", {}, 400, "AGENT_MODEL_INVALID"),
        ("agent_send_model_plan_required_403.json", "gpt-5.6-luna", "normal", {}, 403, "AGENT_MODEL_PLAN_REQUIRED"),
        ("agent_send_model_unavailable_503.json", "gpt-5.6-luna", "max", {"openai_luna_enabled": False}, 503, "AGENT_MODEL_UNAVAILABLE"),
        ("agent_send_model_pricing_503.json", "gpt-6-sol", "max", {}, 503, "AGENT_MODEL_PRICING_NOT_CONFIGURED"),
    ],
)
def test_model_refusals_are_coded(api_client, db, normal_user, max_user, monkeypatch, name, model, plan_user, overrides, status, code):
    settings = _pricing_settings(**overrides)
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    user = max_user if plan_user == "max" else normal_user
    conversation_id = _conversation(api_client, user)
    path = f"/api/agent/conversations/{conversation_id}/messages"

    response = api_client.post(path, json={"content": "Research BTC", "model": model, "client_request_id": "ios-model-000001"}, headers=auth_headers(user))

    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code and isinstance(detail["message"], str)
    assert db.query(AgentRun).filter_by(conversation_id=conversation_id).count() == 0
    _http_fixture(name, "POST", path, response)


# ---------------------------------------------------------------------------
# (b) permission modes
# ---------------------------------------------------------------------------


def test_workspace_capabilities_offer_two_permission_modes(api_client, normal_user):
    response = api_client.get("/api/agent/workspace-capabilities", headers=auth_headers(normal_user))
    assert response.status_code == 200
    body = response.json()
    assert body["permission_modes"] == ["read-only", "workspace-write"]
    assert body["default_permission_mode"] == "workspace-write"
    _http_fixture("agent_workspace_capabilities.json", "GET", "/api/agent/workspace-capabilities", response)


def test_permission_patch_contract(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    path = f"/api/agent/conversations/{conversation_id}"

    ok = api_client.patch(path, json={"permission_mode": "read-only"}, headers=headers)
    assert ok.status_code == 200 and ok.json()["conversation"]["permission_mode"] == "read-only"
    _http_fixture("agent_permission_patch_200.json", "PATCH", path, ok)

    unacknowledged = api_client.patch(path, json={"permission_mode": "full-access"}, headers=headers)
    assert unacknowledged.status_code == 400
    assert unacknowledged.json() == {"detail": "FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED"}
    _http_fixture("agent_permission_full_access_400.json", "PATCH", path, unacknowledged)

    # Acknowledged full-access is stored as what the gate enforces.
    acknowledged = api_client.patch(path, json={"permission_mode": "full-access", "acknowledge_full_access": True}, headers=headers)
    assert acknowledged.status_code == 200
    assert acknowledged.json()["conversation"]["permission_mode"] == "workspace-write"

    conversation = db.get(AgentConversation, conversation_id)
    _seed_run(db, normal_user, status="running", events=[], conversation=conversation)
    busy = api_client.patch(path, json={"permission_mode": "read-only"}, headers=headers)
    assert busy.status_code == 409
    assert busy.json() == {"detail": "CONVERSATION_BUSY"}
    _http_fixture("agent_permission_busy_409.json", "PATCH", path, busy)


def test_the_send_payload_cannot_raise_the_permission_mode(api_client, db, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    assert api_client.patch(f"/api/agent/conversations/{conversation_id}", json={"permission_mode": "read-only"}, headers=headers).status_code == 200

    sent = api_client.post(f"/api/agent/conversations/{conversation_id}/messages",
                           json={"content": "hi", "research_mode": False, "permission_mode": "full-access", "client_request_id": "ios-perm-000001"},
                           headers=headers)

    assert sent.status_code == 200
    question = db.query(AgentMessage).filter_by(conversation_id=conversation_id, role="user").one()
    assert question.context_json["permission_mode"] == "read-only"


# ---------------------------------------------------------------------------
# (c) NAV without an account, (e) decimal strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "path"), [
    ("portfolio_nav_no_account_404.json", "/api/portfolio/nav"),
    ("portfolio_nav_history_no_account_404.json", "/api/portfolio/nav/history"),
    ("portfolio_positions_no_account_404.json", "/api/portfolio/positions"),
])
def test_nav_without_an_account_is_a_coded_404(api_client, normal_user, name, path):
    response = api_client.get(path, headers=auth_headers(normal_user))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"
    _http_fixture(name, "GET", path, response)


def test_nav_money_is_decimal_text(api_client, db, normal_user):
    account = TradingAccount(user_id=normal_user.id, name="Main", venue="MOCK", account_type="LIVE", status="ACTIVE")
    db.add(account)
    db.flush()
    earlier = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    db.add_all([
        NavSnapshot(user_id=normal_user.id, account_id=account.id, nav=Decimal("100000.00000000"), cash=Decimal("25000.50000000"),
                    gross_exposure=Decimal("75000.00000000"), net_exposure=Decimal("75000.00000000"), realized_pnl=Decimal("0E-8"),
                    unrealized_pnl=Decimal("0E-8"), price_timestamp=earlier, calculated_at=earlier, reconciliation_status="ok"),
        NavSnapshot(user_id=normal_user.id, account_id=account.id, nav=Decimal("101234.56789012"), cash=Decimal("25000.50000000"),
                    gross_exposure=Decimal("76234.06789012"), net_exposure=Decimal("-1.00000001"), realized_pnl=Decimal("0E-8"),
                    unrealized_pnl=Decimal("1234.56789012"), price_timestamp=earlier + timedelta(days=1),
                    calculated_at=earlier + timedelta(days=1), reconciliation_status="ok"),
    ])
    db.commit()
    headers = auth_headers(normal_user)
    normalise = _Normaliser()

    current = api_client.get("/api/portfolio/nav", headers=headers)
    assert current.status_code == 200, current.text
    body = current.json()
    nav = body["nav"]
    for field in ("nav", "cash", "gross_exposure", "net_exposure", "realized_pnl", "unrealized_pnl"):
        assert isinstance(nav[field], str) and DECIMAL_TEXT.match(nav[field]), (field, nav[field])
    assert "E" not in json.dumps(body)  # never 0E-8 on the wire
    assert nav["realized_pnl"] == "0.00000000"
    assert body["daily_pnl"] == "1234.56789012" and DECIMAL_TEXT.match(body["daily_return"])
    _http_fixture("portfolio_nav_200.json", "GET", "/api/portfolio/nav", current, normalise)

    history = api_client.get("/api/portfolio/nav/history", headers=headers)
    assert history.status_code == 200
    assert [row["nav"] for row in history.json()["history"]] == ["101234.56789012", "100000.00000000"]
    _http_fixture("portfolio_nav_history_200.json", "GET", "/api/portfolio/nav/history", history, normalise)

    positions = api_client.get("/api/portfolio/positions", headers=headers)
    assert positions.status_code == 200 and positions.json() == {"positions": []}


# ---------------------------------------------------------------------------
# (d) deleted conversations
# ---------------------------------------------------------------------------


def test_a_deleted_conversation_is_a_plain_string_404_everywhere(api_client, normal_user):
    conversation_id = _conversation(api_client, normal_user)
    headers = auth_headers(normal_user)
    assert api_client.delete(f"/api/agent/conversations/{conversation_id}", headers=headers).status_code == 200
    base = f"/api/agent/conversations/{conversation_id}"

    responses = {
        "GET": api_client.get(base, headers=headers),
        "PATCH": api_client.patch(base, json={"title": "x"}, headers=headers),
        "DELETE": api_client.delete(base, headers=headers),
        "GET messages": api_client.get(f"{base}/messages", headers=headers),
        "POST messages": api_client.post(f"{base}/messages", json={"content": "x", "client_request_id": "ios-deleted-0001"}, headers=headers),
    }

    for label, response in responses.items():
        assert response.status_code == 404, label
        assert response.json() == {"detail": "Conversation not found"}, label
    listed = api_client.get("/api/agent/conversations", headers=headers).json()["conversations"]
    assert conversation_id not in {row["id"] for row in listed}
    _http_fixture("agent_conversation_deleted_404.json", "GET", base, responses["GET"])


# ---------------------------------------------------------------------------
# (f) model catalogue
# ---------------------------------------------------------------------------


def test_the_model_catalogue_shape(api_client, normal_user, monkeypatch):
    settings = _pricing_settings()
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)

    response = api_client.get("/api/agent/capabilities", headers=auth_headers(normal_user))

    assert response.status_code == 200
    models = {row["id"]: row for row in response.json()["models"]}
    keys = {"id", "display_name", "description", "provider", "available", "reason", "credit_cost", "category", "capabilities", "estimate", "limits"}
    for row in models.values():
        assert set(row) == keys
        assert row["reason"] in {None, "pricing_not_configured", "plan_required", "unavailable"}
        assert row["category"] in {"generation", "evaluation"}
        assert row["credit_cost"] is None
        assert (row["reason"] is None) == row["available"]
        if row["estimate"] is not None:
            assert set(row["estimate"]) == {"min", "max", "unit", "basis", "task_type"}
        assert set(row["limits"]) == {"plans", "plan_allowed", "image_input"}
    assert models["default"]["available"] is True
    assert models["gpt-5.6-luna"]["reason"] == "plan_required"
    assert models["gpt-6-sol"]["reason"] == "pricing_not_configured" and models["gpt-6-sol"]["estimate"] is None
    assert models["jev"]["category"] == "evaluation" and models["jev"]["capabilities"]["chat"] is False
    _check_fixture("agent_capabilities_models.json", {"request": {"method": "GET", "path": "/api/agent/capabilities"}, "status": 200,
                                                      "body": {"models": _Normaliser()(response.json()["models"])}})


# ---------------------------------------------------------------------------
# (g) replay and reattach
# ---------------------------------------------------------------------------

_REPLAY_EVENTS = [
    (1, "run.started", {"runId": "RUN", "messageId": "MSG", "model": "mock-model", "creditBalance": 25}),
    (2, "plan.ready", {"runId": "RUN", "intent": "market_research", "assets": ["BTC"]}),
    (3, "tool.started", {"toolCallId": "call-1", "tool": "get_market_quote", "arguments": {"symbols": ["BTC"]}}),
    (5, "tool.completed", {"toolCallId": "call-1", "tool": "get_market_quote", "summary": "1 quote", "latencyMs": 12}),
]


def _replay_run(db, user, status: str) -> AgentRun:
    run = _seed_run(db, user, status=status, events=[])
    # A canceled run ends its log with run.canceled. An interrupted run has no
    # terminal frame at all: the client learns the outcome from ``status``.
    terminal = [(6, "run.canceled", {"runId": "RUN", "creditBalance": 30})] if status == "canceled" else []
    for seq, kind, data in _REPLAY_EVENTS + terminal:
        payload = {key: (run.id if value == "RUN" else run.assistant_message_id if value == "MSG" else value) for key, value in data.items()}
        db.add(AgentRunEvent(run_id=run.id, seq=seq, type=kind, data_json={**payload, "seq": seq, "at": f"2026-10-29T08:00:{seq:02d}.000000+00:00"}))
    db.commit()
    return run


@pytest.mark.parametrize("status", ["running", "canceled", "interrupted"])
def test_replay_page_shape(api_client, db, normal_user, status):
    run = _replay_run(db, normal_user, status)
    headers = auth_headers(normal_user)
    path = f"/api/agent/runs/{run.id}/events?after=1"

    response = api_client.get(path, headers=headers)

    assert response.status_code == 200
    page = response.json()
    assert set(page) == {"runId", "status", "messageId", "conversationId", "lastSeq", "truncated", "events"}
    assert page["status"] == status
    assert page["events"][0]["seq"] == 2  # strictly after the cursor
    assert all(set(event) == {"seq", "type", "data"} for event in page["events"])
    # The log can have gaps (ephemeral frames are not stored); lastSeq is the
    # highest stored seq, not a count.
    assert page["lastSeq"] == page["events"][-1]["seq"]
    assert page["truncated"] is False
    _http_fixture(f"agent_run_events_{status}.json", "GET", path, response)

    tail = api_client.get(f"/api/agent/runs/{run.id}/events?after={page['lastSeq']}", headers=headers).json()
    assert tail["events"] == [] and tail["lastSeq"] == page["lastSeq"]


def test_replay_of_someone_elses_run_is_404(api_client, db, normal_user, max_user):
    run = _replay_run(db, normal_user, "running")
    response = api_client.get(f"/api/agent/runs/{run.id}/events", headers=auth_headers(max_user))
    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}
    _http_fixture("agent_run_events_not_found_404.json", "GET", f"/api/agent/runs/{run.id}/events", response)


def test_a_reopened_conversation_names_its_active_run_and_pending_approvals(api_client, db, normal_user):
    run = _replay_run(db, normal_user, "running")
    call = AgentToolCall(run_id=run.id, tool_name="save_watchlist", arguments_json={"symbols": ["BTC"]}, status="awaiting_approval",
                         approval_expires_at=utcnow() + timedelta(minutes=5))
    db.add(call)
    db.commit()
    path = f"/api/agent/conversations/{run.conversation_id}"

    response = api_client.get(path, headers=auth_headers(normal_user))

    assert response.status_code == 200
    body = response.json()
    assert body["active_run_id"] == run.id
    assert body["active_run_message_id"] == run.assistant_message_id
    assert [item["toolCallId"] for item in body["pending_approvals"]] == [call.id]
    assert set(body["pending_approvals"][0]) == {"toolCallId", "tool", "arguments", "expiresAt"}
    _http_fixture("agent_conversation_active_run.json", "GET", path, response)

    # A conversation with nothing running reports nulls, not a stale id.
    finished = _replay_run(db, normal_user, "canceled")
    idle = api_client.get(f"/api/agent/conversations/{finished.conversation_id}", headers=auth_headers(normal_user)).json()
    assert idle["active_run_id"] is None and idle["active_run_message_id"] is None


def test_cancel_reports_the_runs_recorded_status(api_client, db, normal_user):
    run = _replay_run(db, normal_user, "running")
    path = f"/api/agent/runs/{run.id}/cancel"
    response = api_client.post(path, headers=auth_headers(normal_user))
    assert response.status_code == 200
    assert response.json() == {"id": run.id, "status": "canceled"}
    _http_fixture("agent_run_cancel_200.json", "POST", path, response)


# ---------------------------------------------------------------------------
# client versions (§10)
# ---------------------------------------------------------------------------


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_mobile_clients_ship_in_step_and_stay_above_the_server_minimum():
    root = Path(__file__).resolve().parents[2]
    pbxproj = (root / "apps/ios/PureGamma.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    gradle = (root / "apps/android/app/build.gradle.kts").read_text(encoding="utf-8")
    ios_versions = set(re.findall(r"MARKETING_VERSION = ([0-9.]+);", pbxproj))
    android_version = re.search(r'versionName = "([0-9.]+)"', gradle).group(1)
    assert ios_versions == {android_version}, (ios_versions, android_version)

    from apps.api.routers.mobile import APP_MIN_VERSION

    # Raising the minimum forces every older client to upgrade: a product
    # decision, so this test pins it rather than letting it drift.
    assert APP_MIN_VERSION == "1.5.0"
    assert _version(android_version) >= _version(APP_MIN_VERSION)
