"""Resuming a paused LIVE mandate.

The full gate's `mandate_approved` check requires `not paused`, and resume used
to evaluate that gate on the still-paused row - so every resume failed with
"LIVE gates not satisfied: mandate_approved" and a paused mandate could never
trade again. Resume now evaluates the state being requested (unpaused) under
the mandate row lock, and keeps the pause when any other gate fails.
"""
from __future__ import annotations

import pytest

from packages.database.models import TradingMandate
from packages.live_trading import control_plane, kill_switch
from packages.live_trading.control_plane import ControlPlaneError
from tests.conftest import auth_headers
from tests.security.test_live_trading_foundation import _make_live_world


def _paused(db, user, monkeypatch, reason="user stepped away"):
    world = _make_live_world(db, user, monkeypatch)
    control_plane.pause_mandate(db, user.id, world["mandate"].id, reason=reason)
    db.refresh(world["mandate"])
    assert world["mandate"].paused is True
    return world


def test_a_paused_mandate_can_be_resumed_with_the_exact_phrase(db, user_factory, monkeypatch):
    user = user_factory("resume-ok@test.com")
    world = _paused(db, user, monkeypatch)
    mandate = control_plane.resume_mandate(db, user.id, world["mandate"].id, confirmation=f"RESUME {world['mandate'].id}")
    assert mandate.paused is False
    assert mandate.pause_reason is None
    assert mandate.status == "active"


def test_a_wrong_phrase_keeps_the_pause(db, user_factory, monkeypatch):
    user = user_factory("resume-phrase@test.com")
    world = _paused(db, user, monkeypatch)
    with pytest.raises(ControlPlaneError, match="phrase"):
        control_plane.resume_mandate(db, user.id, world["mandate"].id, confirmation="RESUME something-else")
    db.expire_all()
    assert db.get(TradingMandate, world["mandate"].id).paused is True


def test_any_other_failing_gate_keeps_the_pause(db, user_factory, monkeypatch):
    user = user_factory("resume-gate@test.com")
    world = _paused(db, user, monkeypatch)
    world["connection"].status = "DISCONNECTED"
    db.commit()
    with pytest.raises(ControlPlaneError, match="broker_connection_healthy"):
        control_plane.resume_mandate(db, user.id, world["mandate"].id, confirmation=f"RESUME {world['mandate'].id}")
    db.expire_all()
    stored = db.get(TradingMandate, world["mandate"].id)
    assert stored.paused is True
    assert stored.pause_reason == "user stepped away"


def test_reconciliation_and_kill_switch_pauses_need_an_admin(db, user_factory, monkeypatch):
    user = user_factory("resume-admin@test.com")
    world = _paused(db, user, monkeypatch, reason="reconciliation mismatch on BTCUSDT")
    with pytest.raises(ControlPlaneError, match="reconciliation"):
        control_plane.resume_mandate(db, user.id, world["mandate"].id, confirmation=f"RESUME {world['mandate'].id}")

    other = user_factory("resume-kill@test.com")
    world = _paused(db, other, monkeypatch)
    kill_switch.engage(db, scope="mandate", scope_id=world["mandate"].id, reason="ops")
    db.commit()
    with pytest.raises(ControlPlaneError, match="kill switch"):
        control_plane.resume_mandate(db, other.id, world["mandate"].id, confirmation=f"RESUME {world['mandate'].id}")
    db.expire_all()
    assert db.get(TradingMandate, world["mandate"].id).paused is True


def test_resume_over_http_is_owner_scoped(api_client, db, user_factory, monkeypatch):
    owner = user_factory("resume-http@test.com")
    intruder = user_factory("resume-intruder@test.com")
    world = _paused(db, owner, monkeypatch)
    url = f"/api/trading/mandates/{world['mandate'].id}/resume"
    body = {"confirmation": f"RESUME {world['mandate'].id}"}
    assert api_client.post(url, json=body, headers=auth_headers(intruder)).status_code == 404
    response = api_client.post(url, json=body, headers=auth_headers(owner))
    assert response.status_code == 200, response.text
    assert response.json()["mandate"]["paused"] is False
