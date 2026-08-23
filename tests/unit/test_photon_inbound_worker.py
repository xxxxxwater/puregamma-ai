from __future__ import annotations

"""Unit tests for the persistent Photon inbound pipeline (service level).

Covers idempotent enqueue, claim semantics, the reaper, and safe error
metadata without needing a broker or a live Photon endpoint.
"""
from datetime import timedelta

from apps.api.services import photon_inbound_service as service
from packages.database.models import PhotonInboundTask, utcnow


def _insert(db, message_id, status="pending", attempts=0, last_attempt=None, next_retry=None) -> PhotonInboundTask:
    task = PhotonInboundTask(
        message_id=message_id,
        sender="+15555550100",
        content="hello",
        status=status,
        attempt_count=attempts,
        last_attempt_at=last_attempt,
        next_retry_at=next_retry,
    )
    db.add(task)
    db.commit()
    return task


def test_enqueue_creates_row_and_dispatches(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append((task_id, countdown)))

    result = service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    assert result["status"] == "queued"
    task = db.query(PhotonInboundTask).one()
    assert task.message_id == "m1"
    assert dispatched == [(task.id, None)]


def test_enqueue_is_idempotent_per_message_id(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append(task_id))
    service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    second = service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    assert second["status"] == "duplicate"
    assert second["reason"] == "already_queued"
    assert len(dispatched) == 1
    assert db.query(PhotonInboundTask).count() == 1


def test_enqueue_terminal_row_is_duplicate(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append(task_id))
    _insert(db, "m1", status="sent")

    result = service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    assert result == {"status": "duplicate", "reason": "terminal:sent"}
    assert dispatched == []


def test_enqueue_failed_retryable_before_next_retry_is_duplicate(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append(task_id))
    _insert(db, "m1", status="failed_retryable", attempts=1, next_retry=utcnow() + timedelta(minutes=5))

    result = service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    assert result == {"status": "duplicate", "reason": "retry_pending"}
    assert dispatched == []


def test_enqueue_failed_retryable_due_reenqueues(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append(task_id))
    task = _insert(db, "m1", status="failed_retryable", attempts=1, next_retry=utcnow() - timedelta(seconds=1))

    result = service.enqueue_photon_inbound(db, message_id="m1", sender="+15555550100", content="hello")

    assert result["status"] == "queued"
    assert dispatched == [task.id]


def test_claim_skips_terminal_and_fresh_processing(db):
    terminal = _insert(db, "m1", status="sent")
    fresh = _insert(db, "m2", status="processing", last_attempt=utcnow())
    pending = _insert(db, "m3", status="pending")

    assert service._claim(db, terminal.id) is None
    assert service._claim(db, fresh.id) is None
    claimed = service._claim(db, pending.id)
    assert claimed is not None
    assert claimed.status == "processing"
    assert claimed.attempt_count == 1


def test_claim_allows_stale_processing_after_crash(db):
    stale = _insert(db, "m1", status="processing", attempts=1, last_attempt=utcnow() - timedelta(minutes=15))

    claimed = service._claim(db, stale.id)

    assert claimed is not None
    assert claimed.attempt_count == 2


def test_worker_archives_rows_when_provider_not_photon(monkeypatch, db):
    from apps.api.config import Settings

    monkeypatch.setattr("apps.api.config.get_settings", lambda: Settings(imessage_provider="macos_relay"))
    task = _insert(db, "m1", status="pending")

    outcome = service.process_photon_inbound(task.id, db=db)

    assert outcome["status"] == "failed_permanent"
    db.refresh(task)
    assert task.last_error == "photon_provider_disabled"
    assert task.next_retry_at is None


def test_reaper_reenqueues_stale_and_due_rows(monkeypatch, db):
    dispatched: list = []
    monkeypatch.setattr(service, "_dispatch", lambda task_id, countdown=None: dispatched.append(task_id))
    stale = _insert(db, "m1", status="processing", last_attempt=utcnow() - timedelta(minutes=15))
    due = _insert(db, "m2", status="failed_retryable", next_retry=utcnow() - timedelta(seconds=1))
    future = _insert(db, "m3", status="failed_retryable", next_retry=utcnow() + timedelta(minutes=5))
    fresh = _insert(db, "m4", status="processing", last_attempt=utcnow())
    sent = _insert(db, "m5", status="sent")

    result = service.reap_photon_inbound_tasks(db=db)

    assert result["enqueued"] == 2
    assert set(dispatched) == {stale.id, due.id}
    assert future.id not in dispatched
    assert fresh.id not in dispatched
    assert sent.id not in dispatched
