from __future__ import annotations

"""Photon iMessage inbound webhook + async worker integration tests.

The Mac relay route (/internal/imessage/inbound, X-PG-* signing) keeps its
own coverage in test_agent_answer_api.py; these tests cover the NEW Photon
flow: webhook -> persist + Celery enqueue -> worker -> Photon provider reply.
"""
import json
import time

import pytest

from apps.api.config import Settings
from apps.api.routers import imessage_agent
from apps.api.services import agent_answer_service, agent_service, photon_inbound_service
from packages.agents.llm.schemas import LLMStreamChunk
from packages.database.models import (
    AgentRun,
    IMessageInboundEvent,
    NotificationDelivery,
    PhotonInboundTask,
    UserPreference,
    utcnow,
)
from packages.notifications.base import NotificationResult
from packages.notifications.imessage.webhook_gateway import compute_photon_hmac


PHOTON_SECRET = "photon-webhook-test-secret"
PHOTON_LINE = "+14243825596"


def _settings(**overrides) -> Settings:
    return Settings(
        photon_webhook_secret=PHOTON_SECRET,
        photon_line_id=PHOTON_LINE,
        imessage_provider="photon",
        **overrides,
    )


def _payload(message: dict, space: dict | None = None) -> dict:
    return {
        "event": "messages",
        "space": space or {"id": "line-1", "phone": PHOTON_LINE},
        "message": message,
    }


def _signed(payload: dict, timestamp: str | None = None) -> tuple[bytes, dict]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = timestamp or str(int(time.time()))
    signature = compute_photon_hmac(PHOTON_SECRET, ts, body)
    return body, {
        "X-Spectrum-Timestamp": ts,
        "X-Spectrum-Signature": signature,
        "X-Spectrum-Event": "messages",
    }


def _text_message(message_id: str, sender: str, text: str) -> dict:
    return {
        "id": message_id,
        "platform": "iMessage",
        "direction": "inbound",
        "sender": {"id": sender},
        "content": {"type": "text", "text": text},
    }


@pytest.fixture()
def photon_settings(monkeypatch):
    monkeypatch.setattr(imessage_agent, "get_settings", lambda: _settings())
    # The worker reads the global settings for its provider guard.
    monkeypatch.setattr("apps.api.config.get_settings", lambda: _settings())


class EchoProvider:
    provider_name = "mock"
    model = "echo-model"

    def stream_chat(self, messages, **kwargs):
        yield LLMStreamChunk(delta="echo reply", provider="mock", model="echo-model")
        yield LLMStreamChunk(done=True, provider="mock", model="echo-model", prompt_tokens=4, completion_tokens=4)


@pytest.fixture()
def photon_echo_llm(monkeypatch):
    settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="echo-model")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: EchoProvider())
    monkeypatch.setattr(agent_answer_service, "get_settings", lambda: settings)


@pytest.fixture()
def no_dispatch(monkeypatch):
    """Record enqueues instead of publishing to a broker."""
    dispatched: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        photon_inbound_service,
        "_dispatch",
        lambda task_id, countdown=None: dispatched.append((task_id, countdown)),
    )
    return dispatched


@pytest.fixture()
def fake_photon(monkeypatch):
    """PhotonIMessageProvider stand-in capturing send_message calls."""
    class FakePhoton:
        def __init__(self):
            self.sent: list[tuple[str, str, str]] = []
            self.outcomes = [NotificationResult(True, "imessage", {"ok": True, "message_id": "out-1"})]

        def send_message(self, recipient, message, idempotency_key):
            self.sent.append((recipient, message, idempotency_key))
            return self.outcomes[0] if len(self.outcomes) == 1 else self.outcomes.pop(0)

    fake = FakePhoton()
    monkeypatch.setattr(photon_inbound_service, "PhotonIMessageProvider", lambda: fake)
    return fake


def _verify_pro_user(db, pro_user, recipient="+15555559999") -> None:
    preference = db.query(UserPreference).filter_by(user_id=pro_user.id).one()
    preference.imessage_recipient = recipient
    preference.imessage_recipient_verified_at = utcnow()
    db.commit()


# ---------------------------------------------------------------------------
# Signature / replay protection (unchanged protocol)
# ---------------------------------------------------------------------------


def test_photon_webhook_rejects_invalid_signature(api_client, photon_settings):
    body, headers = _signed(_payload(_text_message("m1", "+15555550100", "hi")))
    headers["X-Spectrum-Signature"] = "deadbeef"
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_photon_signature"


def test_photon_webhook_rejects_missing_headers(api_client, photon_settings):
    body, _ = _signed(_payload(_text_message("m1", "+15555550100", "hi")))
    response = api_client.post("/internal/imessage/photon/webhook", content=body)
    assert response.status_code == 401


def test_photon_webhook_rejects_expired_timestamp(api_client, photon_settings):
    payload = _payload(_text_message("m1", "+15555550100", "hi"))
    body, headers = _signed(payload, timestamp=str(int(time.time()) - 600))
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Event / line / direction / content filtering
# ---------------------------------------------------------------------------


def test_photon_webhook_ignores_unknown_event(api_client, photon_settings):
    body, headers = _signed(_payload(_text_message("m1", "+15555550100", "hi")))
    headers["X-Spectrum-Event"] = "message.delivered"
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "unsupported_event:message.delivered"


def test_photon_webhook_ignores_unknown_payload_event(api_client, photon_settings):
    payload = _payload(_text_message("m1", "+15555550100", "hi"))
    payload["event"] = "message.delivered"
    body, headers = _signed(payload)
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_photon_webhook_ignores_wrong_line(api_client, photon_settings):
    payload = _payload(_text_message("m1", "+15555550100", "hi"), space={"id": "line-other", "phone": "+19998887777"})
    body, headers = _signed(payload)
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "line_mismatch"}


def test_photon_webhook_ignores_outbound_echo(api_client, photon_settings):
    message = _text_message("m-out", "+15555550100", "hi")
    message["direction"] = "outbound"
    body, headers = _signed(_payload(message))
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "not_inbound_imessage"


def test_photon_webhook_marks_non_text_attachment_unprocessed(api_client, db, photon_settings):
    message = {
        "id": "m-img",
        "platform": "iMessage",
        "direction": "inbound",
        "sender": {"id": "+15555550100"},
        "content": {"type": "image", "url": "https://cdn.example/img.png"},
    }
    body, headers = _signed(_payload(message))
    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unprocessed"
    assert data["reason"] == "unsupported_content_type:image"
    # Nothing persisted for the unprocessed attachment.
    assert db.query(PhotonInboundTask).count() == 0


# ---------------------------------------------------------------------------
# Fast acknowledge + idempotent enqueue
# ---------------------------------------------------------------------------


def test_photon_webhook_persists_enqueues_and_returns_fast(api_client, db, pro_user, photon_settings, photon_echo_llm, no_dispatch):
    _verify_pro_user(db, pro_user)
    body, headers = _signed(_payload(_text_message("photon-msg-1", "+15555559999", "hello photon")))

    response = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "queued", data
    # The webhook never ran the agent (fast 2xx; worker does the LLM work).
    assert db.query(AgentRun).count() == 0
    task = db.query(PhotonInboundTask).one()
    assert task.message_id == "photon-msg-1"
    assert task.sender == "+15555559999"
    assert task.content == "hello photon"
    assert task.status == "pending"
    assert no_dispatch == [(task.id, None)]

    # Redelivery of the same message.id must not enqueue twice.
    duplicate = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["reason"] == "already_queued"
    assert len(no_dispatch) == 1
    assert db.query(PhotonInboundTask).count() == 1


# ---------------------------------------------------------------------------
# Worker: shared agent flow -> Photon provider reply
# ---------------------------------------------------------------------------


def test_photon_worker_sends_reply_through_provider(api_client, db, pro_user, photon_settings, photon_echo_llm, no_dispatch, fake_photon):
    _verify_pro_user(db, pro_user)
    body, headers = _signed(_payload(_text_message("photon-msg-2", "+15555559999", "hello photon")))
    queued = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()
    assert queued["status"] == "queued"

    outcome = photon_inbound_service.process_photon_inbound(queued["task_id"], db=db)

    assert outcome["status"] == "sent", outcome
    assert len(fake_photon.sent) == 1
    recipient, message, idempotency_key = fake_photon.sent[0]
    assert recipient == "+15555559999"
    assert message == "echo reply"
    assert idempotency_key == "photon-inbound-reply:photon-msg-2"
    task = db.query(PhotonInboundTask).one()
    assert task.status == "sent"
    assert task.last_error is None
    delivery = db.query(NotificationDelivery).filter_by(idempotency_key="photon-inbound-reply:photon-msg-2").one()
    assert delivery.status == "sent"
    assert delivery.user_id == pro_user.id
    assert delivery.payload["type"] == "photon_inbound_reply"
    assert task.outbound_delivery_id == delivery.id
    # The agent ran exactly once, through the shared flow.
    assert db.query(AgentRun).count() == 1
    assert db.query(IMessageInboundEvent).filter_by(relay_message_id="photon-msg-2").count() == 1
    # A terminal redelivery is acknowledged without another enqueue.
    redelivery = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()
    assert redelivery["status"] == "duplicate"
    assert redelivery["reason"] == "terminal:sent"
    assert len(no_dispatch) == 1


def test_photon_worker_retries_after_provider_failure(api_client, db, pro_user, photon_settings, photon_echo_llm, no_dispatch, fake_photon):
    _verify_pro_user(db, pro_user)
    fake_photon.outcomes = [
        NotificationResult(False, "imessage", {"status": "failed_retryable", "error": "HTTP_502"}),
        NotificationResult(True, "imessage", {"ok": True, "message_id": "out-2"}),
    ]
    body, headers = _signed(_payload(_text_message("photon-msg-3", "+15555559999", "hello photon")))
    queued = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()

    first = photon_inbound_service.process_photon_inbound(queued["task_id"], db=db)
    assert first["status"] == "failed_retryable", first
    task = db.query(PhotonInboundTask).one()
    assert task.attempt_count == 1
    assert task.last_error == "photon_reply_failed"
    assert task.next_retry_at is not None
    # The retry was scheduled on Celery (countdown = 60s for the first delay).
    assert no_dispatch[-1] == (task.id, 60)
    delivery = db.query(NotificationDelivery).filter_by(idempotency_key="photon-inbound-reply:photon-msg-3").one()
    assert delivery.status == "failed_retryable"

    second = photon_inbound_service.process_photon_inbound(queued["task_id"], db=db)
    assert second["status"] == "sent", second
    db.refresh(task)
    assert task.attempt_count == 2
    assert task.status == "sent"
    db.refresh(delivery)
    assert delivery.status == "sent"
    # The agent still ran exactly once: the shared flow deduped on retry.
    assert db.query(AgentRun).count() == 1
    assert db.query(NotificationDelivery).filter_by(idempotency_key="photon-inbound-reply:photon-msg-3").count() == 1


def test_photon_worker_exhausts_retries_and_goes_permanent(api_client, db, pro_user, photon_settings, photon_echo_llm, no_dispatch, fake_photon):
    _verify_pro_user(db, pro_user)
    fake_photon.outcomes = [NotificationResult(False, "imessage", {"status": "failed_retryable", "error": "HTTP_502"})]
    body, headers = _signed(_payload(_text_message("photon-msg-4", "+15555559999", "hello photon")))
    queued = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()
    task_id = queued["task_id"]

    outcomes = [photon_inbound_service.process_photon_inbound(task_id, db=db)["status"] for _ in range(3)]

    assert outcomes == ["failed_retryable", "failed_retryable", "failed_permanent"], outcomes
    task = db.query(PhotonInboundTask).one()
    assert task.status == "failed_permanent"
    assert task.last_error == "photon_reply_failed"
    # The agent ran once; retries never re-billed or re-ran it.
    assert db.query(AgentRun).count() == 1


def test_photon_worker_unverified_sender_marks_no_reply(api_client, db, photon_settings, no_dispatch):
    body, headers = _signed(_payload(_text_message("photon-msg-5", "+15555551234", "hello")))
    queued = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()
    assert queued["status"] == "queued"

    outcome = photon_inbound_service.process_photon_inbound(queued["task_id"], db=db)

    assert outcome["status"] == "no_reply", outcome
    task = db.query(PhotonInboundTask).one()
    assert task.status == "no_reply"
    assert db.query(AgentRun).count() == 0
    assert db.query(IMessageInboundEvent).count() == 0
    assert db.query(NotificationDelivery).count() == 0


def test_photon_worker_permanent_provider_failure(api_client, db, pro_user, photon_settings, photon_echo_llm, no_dispatch, fake_photon):
    _verify_pro_user(db, pro_user)
    fake_photon.outcomes = [NotificationResult(False, "imessage", {"status": "invalid_recipient", "error": "VALIDATION_ERROR"})]
    body, headers = _signed(_payload(_text_message("photon-msg-6", "+15555559999", "hello photon")))
    queued = api_client.post("/internal/imessage/photon/webhook", content=body, headers=headers).json()

    outcome = photon_inbound_service.process_photon_inbound(queued["task_id"], db=db)

    assert outcome["status"] == "failed_permanent", outcome
    task = db.query(PhotonInboundTask).one()
    assert task.last_error == "photon_reply_permanent"
    delivery = db.query(NotificationDelivery).filter_by(idempotency_key="photon-inbound-reply:photon-msg-6").one()
    assert delivery.status == "failed_permanent"
