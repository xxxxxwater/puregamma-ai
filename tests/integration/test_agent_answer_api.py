"""Integration tests for the unified conversational entry (P0-4).

Fast-path answers are evidence-grounded: seeded research facts must show up in
the answer, a machine-readable envelope is persisted on the assistant message
and emitted as the ``answer.envelope`` SSE event right before
``message.completed``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from apps.api.config import Settings
from apps.api.routers import imessage_agent
from apps.api.services import agent_answer_service, agent_service, options_service
from packages.agents.llm.schemas import LLMStreamChunk
from packages.database.models import (
    AgentMessage,
    AgentRun,
    IMessageInboundEvent,
    MarketEvent,
    ResearchSnapshot,
    UserPreference,
    utcnow,
)
from tests.conftest import auth_headers


class EchoProvider:
    """Offline provider that echoes the phrasing prompt back, so assertions can
    verify that the deterministic facts (and only those) reached the model."""

    provider_name = "mock"
    model = "echo-model"
    configured = True
    last_error = None

    def stream_chat(self, messages, **kwargs):
        payload = "\n".join(message.content for message in messages)
        yield LLMStreamChunk(delta=payload[:8000], provider="mock", model="echo-model")
        yield LLMStreamChunk(done=True, provider="mock", model="echo-model", prompt_tokens=64, completion_tokens=256)


@pytest.fixture()
def agent_echo_llm(monkeypatch):
    settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="echo-model")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: EchoProvider())
    monkeypatch.setattr(agent_answer_service, "get_settings", lambda: settings)


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if name:
            events.append((name, json.loads(data) if data else {}))
    return events


def _post_message(api_client, user, content: str, locale: str = "zh") -> tuple[str, str]:
    created = api_client.post("/api/agent/conversations", json={"title": "answers"}, headers=auth_headers(user))
    conversation_id = created.json()["conversation"]["id"]
    response = api_client.post(
        f"/api/agent/conversations/{conversation_id}/messages",
        json={"content": content, "locale": locale},
        headers=auth_headers(user),
    )
    assert response.status_code == 200, response.text
    return conversation_id, response.text


def _seed_research(db) -> tuple[ResearchSnapshot, MarketEvent]:
    now = utcnow()
    snapshot = ResearchSnapshot(
        kind="intraday",
        as_of=now,
        data_cutoff_at=now,
        window_start=now - timedelta(hours=24),
        window_end=now,
        status="completed",
        health_json={},
        source_counts_json={"news": 1},
    )
    db.add(snapshot)
    db.flush()
    event = MarketEvent(
        event_type="news",
        title="Bitcoin rallies on stored ETF inflows",
        summary="Stored evidence summary for the overnight brief.",
        source_provider="news:rss",
        source_url="https://example.com/btc-etf-inflows",
        source_published_at=now - timedelta(hours=3),
        collected_at=now,
        data_cutoff_at=now,
        fingerprint="fp-agent-answer-overnight-1",
        assets=["BTC"],
        direction=None,
        time_horizon="intraday",
        confidence=0.9,
        evidence_json=[{"kind": "news_document", "ref": "doc-1", "url": "https://example.com/btc-etf-inflows", "published_at": now.isoformat()}],
        evidence_gaps=[],
        research_snapshot_id=snapshot.id,
        status="active",
    )
    db.add(event)
    db.commit()
    return snapshot, event


def test_overnight_fast_path_emits_envelope_before_completion(api_client, db, pro_user, agent_echo_llm):
    _seed_research(db)

    conversation_id, text = _post_message(api_client, pro_user, "隔夜有什么重要的事？", "zh")

    assert "event: run.started" in text
    assert "event: plan.ready" in text
    assert "event: answer.envelope" in text
    assert "event: message.completed" in text
    assert text.index("event: answer.envelope") < text.index("event: message.completed")
    # The phrasing model echoed the evidence pack: the seeded event title is in the answer.
    assert "Bitcoin rallies on stored ETF inflows" in text

    events = _sse_events(text)
    envelope = next(data for name, data in events if name == "answer.envelope")
    assert envelope["intent"] == "overnight_brief"
    assert envelope["as_of"]
    assert any(source["url"] == "https://example.com/btc-etf-inflows" for source in envelope["sources"])
    assert all(set(source) <= {"provider", "url", "published_at"} for source in envelope["sources"])
    assert 0 <= envelope["confidence"] <= 1
    assert envelope["next_actions"]
    assert {"action_type", "title"} <= set(envelope["next_actions"][0])
    assert envelope["credits"]["reserved"] >= 0
    assert envelope["credits"]["settled"] >= 0
    assert isinstance(envelope["degraded"], bool)

    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()
    assert run.status == "completed"
    assistant = db.get(AgentMessage, run.assistant_message_id)
    assert assistant.status == "completed"
    assert assistant.context_json["answer_envelope"]["intent"] == "overnight_brief"
    assert assistant.context_json["answer_envelope"]["as_of"] == envelope["as_of"]

    # No secret material anywhere in the envelope.
    blob = json.dumps(envelope, ensure_ascii=False).lower()
    for marker in ("api_key", "apikey", "secret", "bearer", "password"):
        assert marker not in blob


def test_portfolio_intent_disconnected_user_degrades_explicitly(api_client, db, pro_user, agent_echo_llm):
    conversation_id, text = _post_message(api_client, pro_user, "我的投资组合怎么样？", "zh")

    events = _sse_events(text)
    envelope = next(data for name, data in events if name == "answer.envelope")
    assert envelope["intent"] == "portfolio_review"
    assert envelope["portfolio_impact"] == {"connected": False}
    assert envelope["degraded"] is True

    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()
    assistant = db.get(AgentMessage, run.assistant_message_id)
    # The answer only echoes the evidence pack: disconnected is stated, no holdings invented.
    assert '"connected": false' in assistant.content
    assert "BTC" not in assistant.content


def test_long_gamma_fast_path_cites_expiry_strike_source(api_client, db, pro_user, agent_echo_llm, monkeypatch):
    now = datetime.now(timezone.utc)
    expiry = (now + timedelta(days=30)).isoformat()
    chain = {
        "provider": "deribit",
        "status": "HEALTHY",
        "currency": "BTC",
        "source_url": "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
        "fetched_at": now.isoformat(),
        "instruments": [
            {
                "instrument": "BTC-28AUG26-100000-C",
                "option_type": "call",
                "strike": 100000.0,
                "expiry": expiry,
                "mark_iv": 55.0,
                "underlying_price": 98000.0,
                "volume_24h": 120.0,
                "open_interest": 800.0,
                "spread_pct": 0.02,
                "greeks": {"gamma": 0.0002, "theta": -45.0},
            }
        ],
        "live_trading": False,
    }
    monkeypatch.setattr(options_service, "get_option_chain", lambda currency, force=False: chain)

    conversation_id, text = _post_message(api_client, pro_user, "今天有什么长伽马机会？", "zh")

    events = _sse_events(text)
    envelope = next(data for name, data in events if name == "answer.envelope")
    assert envelope["intent"] == "long_gamma_scan"
    assert envelope["sources"]
    assert any("deribit.com" in (source["url"] or "") for source in envelope["sources"])

    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()
    assistant = db.get(AgentMessage, run.assistant_message_id)
    assert "100000" in assistant.content
    assert expiry[:10] in assistant.content
    assert "deribit" in assistant.content


def test_unrelated_message_uses_existing_tool_chain(api_client, db, pro_user, agent_echo_llm):
    _seed_research(db)

    conversation_id, text = _post_message(api_client, pro_user, "What is the BTC market price?", "en")

    assert "event: message.completed" in text
    assert "event: answer.envelope" not in text
    run = db.query(AgentRun).filter_by(conversation_id=conversation_id).one()
    assistant = db.get(AgentMessage, run.assistant_message_id)
    assert "answer_envelope" not in (assistant.context_json or {})


# ---------------------------------------------------------------------------
# iMessage voice wiring
# ---------------------------------------------------------------------------


def _signed_body(payload: dict, secret: str) -> tuple[bytes, dict]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {"X-PG-Timestamp": timestamp, "X-PG-Signature": signature}


def test_imessage_voice_inbound_runs_answer_chain_and_dedupes(api_client, db, pro_user, agent_echo_llm, monkeypatch):
    from apps.api.services import imessage_voice_service

    secret = "imessage-voice-test-secret"
    monkeypatch.setattr(imessage_agent, "get_settings", lambda: Settings(imessage_relay_secret=secret))
    monkeypatch.setattr(
        imessage_voice_service,
        "transcribe_audio",
        lambda db, user, audio, extension, locale: "隔夜有什么重要的事？",
    )
    monkeypatch.setattr(imessage_voice_service, "synthesize_voice", lambda db, user, text, locale: b"mp3-voice-bytes")

    preference = db.query(UserPreference).filter_by(user_id=pro_user.id).one()
    preference.imessage_recipient = "+15555559999"
    preference.imessage_recipient_verified_at = utcnow()
    db.commit()

    payload = {
        "message_id": "voice-msg-1",
        "sender": "+15555559999",
        "content": "",
        "audio_base64": base64.b64encode(b"\x01" * 1024).decode(),
        "audio_mime": "audio/mpeg",
    }
    body, headers = _signed_body(payload, secret)

    response = api_client.post("/internal/imessage/inbound", content=body, headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed", data
    assert data["reply_text"]
    assert base64.b64decode(data["reply_audio_base64"]) == b"mp3-voice-bytes"
    assert data["reply_audio_mime"] == "audio/mpeg"

    event = db.query(IMessageInboundEvent).filter_by(relay_message_id="voice-msg-1").one()
    assert event.status == "completed"
    assert event.assistant_message_id

    # The voice turn persisted into the same "iMessage Agent" conversation the
    # text thread uses.
    run = db.query(AgentRun).filter_by(user_id=pro_user.id).one()
    assistant = db.get(AgentMessage, run.assistant_message_id)
    assert assistant.status == "completed"
    assert assistant.context_json["answer_envelope"]["intent"] == "overnight_brief"
    user_message = db.get(AgentMessage, run.user_message_id)
    assert user_message.content == "隔夜有什么重要的事？"

    runs_before = db.query(AgentRun).count()
    duplicate = api_client.post("/internal/imessage/inbound", content=body, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert db.query(AgentRun).count() == runs_before

    # No secret material in the voice reply payload.
    blob = json.dumps(data).lower()
    for marker in ("api_key", "secret", "bearer"):
        assert marker not in blob
