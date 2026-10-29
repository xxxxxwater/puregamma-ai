"""LIVE mandate proposals: propose -> two different administrators -> effect.

Pins: off by default (404) and 503 when the migration is missing; the
proposer and the owner can never approve; one administrator cannot approve
twice; expiry, revocation and rejection are terminal; a kill switch keeps a
proposal from taking effect; an effective mandate starts paused and still
cannot trade past the deployment's static gate; terms are validated; every
transition is audited.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from apps.api.config import get_settings
from packages.database.models import TradingAuditLog, TradingMandate, TradingMandateProposal
from packages.live_trading import control_plane, flags, kill_switch, mandate_proposals
from packages.live_trading.control_plane import OrderRejected
from tests.conftest import auth_headers
from tests.security.test_live_trading_foundation import _make_live_world


def _enable(monkeypatch, **overrides):
    settings = dataclasses.replace(get_settings(), live_mandate_proposals_enabled=True, **overrides)
    monkeypatch.setattr(mandate_proposals, "get_settings", lambda: settings)
    return settings


def _terms(world, **overrides):
    terms = {
        "account_id": world["account"].id,
        "strategy_release_id": world["release"].id,
        "broker_connection_id": world["connection"].id,
        "allowed_symbols": ["btcusdt"],
        "allowed_side": "long",
        "max_total_notional": "5000",
        "max_per_order_notional": "500",
        "max_position_notional": "2000",
        "max_daily_loss": "200",
        "max_leverage": "1",
        "max_trades_per_day": 10,
        "max_order_frequency_seconds": 30,
    }
    terms.update(overrides)
    return terms


@pytest.fixture()
def people(user_factory):
    return {
        "owner": user_factory("mp-owner@test.com"),
        "stranger": user_factory("mp-stranger@test.com"),
        "admin_a": user_factory("mp-admin-a@test.com", role="admin"),
        "admin_b": user_factory("mp-admin-b@test.com", role="admin"),
        "admin_c": user_factory("mp-admin-c@test.com", role="admin"),
    }


def _propose(api_client, owner, world, **terms):
    response = api_client.post(
        "/api/trading/mandate-proposals",
        json={"terms": _terms(world, **terms), "reason": "start BTC DCA"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


def _approve(api_client, admin, proposal_id, note="checked limits"):
    return api_client.post(f"/admin/trading/mandate-proposals/{proposal_id}/approve", json={"note": note}, headers=auth_headers(admin))


def test_off_by_default_every_route_is_a_404(api_client, db, people):
    assert get_settings().live_mandate_proposals_enabled is False
    owner, admin = people["owner"], people["admin_a"]
    calls = [
        (owner, "get", "/api/trading/mandate-proposals", None),
        (owner, "post", "/api/trading/mandate-proposals", {"terms": {}, "reason": "x"}),
        (owner, "post", "/api/trading/mandate-proposals/p1/revoke", {"reason": "x"}),
        (admin, "get", "/admin/trading/mandate-proposals", None),
        (admin, "post", "/admin/trading/mandate-proposals/p1/approve", {"note": "x"}),
        (admin, "post", "/admin/trading/mandate-proposals/p1/reject", {"note": "x"}),
    ]
    for actor, method, path, body in calls:
        kwargs = {"headers": auth_headers(actor), **({"json": body} if body is not None else {})}
        response = getattr(api_client, method)(path, **kwargs)
        assert response.status_code == 404, path
        assert response.json()["detail"]["code"] == "MANDATE_PROPOSALS_DISABLED"
    assert db.query(TradingMandateProposal).count() == 0


def test_missing_migration_answers_503_not_500(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    db.execute(text("DROP TABLE trading_mandate_proposals"))
    db.commit()
    response = api_client.get("/api/trading/mandate-proposals", headers=auth_headers(people["owner"]))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MANDATE_PROPOSALS_UNAVAILABLE"
    assert "0036" in response.json()["detail"]["message"]
    db.execute(text("CREATE TABLE trading_mandate_proposals (id VARCHAR PRIMARY KEY)"))  # let teardown drop it
    db.commit()


def test_two_different_admins_make_it_effective_but_paused_and_still_gated(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    world = _make_live_world(db, owner, monkeypatch)  # also enables the static gate for this test
    proposal = _propose(api_client, owner, world)
    assert proposal["status"] == "pending" and proposal["terms"]["allowed_symbols"] == ["BTCUSDT"]
    assert proposal["terms"]["max_total_notional"] == "5000"

    first = _approve(api_client, people["admin_a"], proposal["id"])
    assert first.status_code == 200 and first.json()["proposal"]["status"] == "pending"
    assert db.query(TradingMandate).count() == 1  # only the world's mandate

    second = _approve(api_client, people["admin_b"], proposal["id"])
    assert second.status_code == 200, second.text
    applied = second.json()["proposal"]
    assert applied["status"] == "applied" and len(applied["approvals"]) == 2
    mandate = db.get(TradingMandate, applied["applied_mandate_id"])
    assert mandate.paused is True and mandate.pause_reason == mandate_proposals.NEW_MANDATE_PAUSE_REASON
    assert mandate.approval_status == "approved" and mandate.approved_by == people["admin_b"].id
    assert mandate.max_total_notional == Decimal("5000") and mandate.allowed_symbols_json == ["BTCUSDT"]
    assert mandate.audit_metadata_json["approvers"] == [people["admin_a"].id, people["admin_b"].id]

    # Effective is not trading: paused, so the gate refuses; and with the
    # deployment's static gate off it is refused regardless.
    with pytest.raises(OrderRejected):
        control_plane.preview_order(db, owner.id, mandate_id=mandate.id, symbol="BTCUSDT", side="buy", quantity="0.1")
    monkeypatch.setattr(flags, "evaluate_static_gate", lambda: flags.GateResult(enabled=False, checks={"live_trading_enabled": {"ok": False, "detail": False}}))
    mandate.paused = False
    db.commit()
    with pytest.raises(OrderRejected, match="LIVE disabled"):
        control_plane.preview_order(db, owner.id, mandate_id=mandate.id, symbol="BTCUSDT", side="buy", quantity="0.1")

    actions = [row.action for row in db.query(TradingAuditLog).filter(TradingAuditLog.action.like("LIVE_MANDATE_%")).order_by(TradingAuditLog.created_at).all()]
    assert actions == ["LIVE_MANDATE_PROPOSED", "LIVE_MANDATE_PROPOSAL_APPROVED", "LIVE_MANDATE_PROPOSAL_APPROVED"]
    # Applied is terminal.
    assert _approve(api_client, people["admin_c"], proposal["id"]).status_code == 409


def test_the_proposer_cannot_approve_their_own_proposal(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    world = _make_live_world(db, owner, monkeypatch)
    response = api_client.post(
        "/admin/trading/mandate-proposals",
        json={"user_id": owner.id, "terms": _terms(world), "reason": "ops setup"},
        headers=auth_headers(people["admin_a"]),
    )
    proposal = response.json()["proposal"]
    assert proposal["proposed_by"] == people["admin_a"].id
    own = _approve(api_client, people["admin_a"], proposal["id"])
    assert own.status_code == 403 and "proposer" in own.json()["detail"]["message"]
    assert db.get(TradingMandateProposal, proposal["id"]).approvals_json == []


def test_an_admin_who_owns_the_mandate_cannot_approve_it(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    admin_owner = people["admin_c"]
    world = _make_live_world(db, admin_owner, monkeypatch)
    proposal = _propose(api_client, admin_owner, world)
    response = _approve(api_client, admin_owner, proposal["id"])
    assert response.status_code == 403


def test_the_same_admin_cannot_approve_twice(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    assert _approve(api_client, people["admin_a"], proposal["id"]).status_code == 200
    again = _approve(api_client, people["admin_a"], proposal["id"])
    assert again.status_code == 403 and "twice" in again.json()["detail"]["message"]
    row = db.get(TradingMandateProposal, proposal["id"])
    db.refresh(row)
    assert row.status == "pending" and len(row.approvals_json) == 1


def test_a_normal_user_cannot_approve(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    assert _approve(api_client, people["stranger"], proposal["id"]).status_code == 403
    assert _approve(api_client, owner, proposal["id"]).status_code == 403


def test_an_expired_proposal_cannot_be_approved(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    assert _approve(api_client, people["admin_a"], proposal["id"]).status_code == 200
    row = db.get(TradingMandateProposal, proposal["id"])
    row.expires_at = row.expires_at - timedelta(days=30)
    db.commit()
    listed = api_client.get("/api/trading/mandate-proposals", headers=auth_headers(owner)).json()["proposals"]
    assert listed[0]["status"] == "expired"
    late = _approve(api_client, people["admin_b"], proposal["id"])
    assert late.status_code == 409 and "expired" in late.json()["detail"]["message"]
    db.expire_all()
    assert db.get(TradingMandateProposal, proposal["id"]).status == "expired"
    assert db.query(TradingMandate).count() == 1
    assert db.query(TradingAuditLog).filter_by(action="LIVE_MANDATE_PROPOSAL_EXPIRED").count() == 1


def test_a_revoked_proposal_is_final_and_only_its_people_can_revoke(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    stranger = api_client.post(f"/api/trading/mandate-proposals/{proposal['id']}/revoke", json={"reason": "x"}, headers=auth_headers(people["stranger"]))
    missing = api_client.post("/api/trading/mandate-proposals/nope/revoke", json={"reason": "x"}, headers=auth_headers(people["stranger"]))
    assert stranger.status_code == missing.status_code == 404
    assert stranger.json() == missing.json()
    assert api_client.get("/api/trading/mandate-proposals", headers=auth_headers(people["stranger"])).json()["proposals"] == []

    assert _approve(api_client, people["admin_a"], proposal["id"]).status_code == 200
    revoked = api_client.post(f"/api/trading/mandate-proposals/{proposal['id']}/revoke", json={"reason": "changed my mind"}, headers=auth_headers(owner))
    assert revoked.status_code == 200 and revoked.json()["proposal"]["status"] == "revoked"
    assert _approve(api_client, people["admin_b"], proposal["id"]).status_code == 409
    assert db.query(TradingMandate).count() == 1


def test_rejection_is_final(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    rejected = api_client.post(f"/admin/trading/mandate-proposals/{proposal['id']}/reject", json={"note": "limits too wide"}, headers=auth_headers(people["admin_a"]))
    assert rejected.json()["proposal"]["status"] == "rejected"
    assert rejected.json()["proposal"]["decision_reason"] == "limits too wide"
    assert _approve(api_client, people["admin_b"], proposal["id"]).status_code == 409


def test_a_kill_switch_keeps_the_proposal_from_taking_effect(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch))
    assert _approve(api_client, people["admin_a"], proposal["id"]).status_code == 200
    kill_switch.engage(db, scope="user", scope_id=owner.id, reason="review")
    db.commit()
    blocked = _approve(api_client, people["admin_b"], proposal["id"])
    assert blocked.status_code == 409 and "kill switch" in blocked.json()["detail"]["message"]
    db.expire_all()
    row = db.get(TradingMandateProposal, proposal["id"])
    assert row.status == "pending" and len(row.approvals_json) == 1
    kill_switch.release(db, scope="user", scope_id=owner.id, resolved_by=people["admin_a"].id)
    db.commit()
    assert _approve(api_client, people["admin_b"], proposal["id"]).json()["proposal"]["status"] == "applied"


def test_effect_requires_the_owners_approved_cap(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    proposal = _propose(api_client, owner, _make_live_world(db, owner, monkeypatch), max_total_notional="50000", max_position_notional="2000")
    assert _approve(api_client, people["admin_a"], proposal["id"]).status_code == 200
    over = _approve(api_client, people["admin_b"], proposal["id"])
    assert over.status_code == 400 and "cap" in over.json()["detail"]["message"]
    db.expire_all()
    row = db.get(TradingMandateProposal, proposal["id"])
    assert row.status == "pending" and len(row.approvals_json) == 1
    assert db.query(TradingMandate).count() == 1


def test_an_amendment_applies_once_and_refuses_a_stale_revision(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner = people["owner"]
    world = _make_live_world(db, owner, monkeypatch)
    mandate = world["mandate"]
    amend = lambda total: api_client.post(  # noqa: E731
        "/api/trading/mandate-proposals",
        json={"terms": _terms(world, max_total_notional=total), "target_mandate_id": mandate.id, "reason": "resize"},
        headers=auth_headers(owner),
    ).json()["proposal"]
    first, stale = amend("3000"), amend("4000")
    assert first["kind"] == "amend" and first["base_revision"] == 1
    _approve(api_client, people["admin_a"], first["id"])
    assert _approve(api_client, people["admin_b"], first["id"]).json()["proposal"]["status"] == "applied"
    db.refresh(mandate)
    assert mandate.max_total_notional == Decimal("3000") and mandate.revision == 2

    _approve(api_client, people["admin_a"], stale["id"])
    conflict = _approve(api_client, people["admin_b"], stale["id"])
    assert conflict.status_code == 409 and "changed" in conflict.json()["detail"]["message"]
    db.refresh(mandate)
    assert mandate.max_total_notional == Decimal("3000")


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({"max_per_order_notional": "3000"}, "per-order"),
        ({"max_leverage": "2"}, "spot only"),
        ({"allowed_side": "short"}, "allowed_side"),
        ({"allowed_symbols": []}, "allowed_symbols"),
        ({"max_total_notional": 5000.0}, "decimal string"),
        ({"max_daily_loss": "-1"}, "positive"),
        ({"max_trades_per_day": 0}, "max_trades_per_day"),
        ({"strategy_release_id": "not-mine"}, "strategy_release_id"),
    ],
)
def test_terms_are_validated(api_client, db, people, monkeypatch, override, fragment):
    _enable(monkeypatch)
    owner = people["owner"]
    world = _make_live_world(db, owner, monkeypatch)
    response = api_client.post(
        "/api/trading/mandate-proposals", json={"terms": _terms(world, **override), "reason": "x"}, headers=auth_headers(owner)
    )
    assert response.status_code == 400
    assert fragment in response.json()["detail"]["message"]
    assert db.query(TradingMandateProposal).count() == 0


def test_another_users_account_cannot_be_bound(api_client, db, people, monkeypatch):
    _enable(monkeypatch)
    owner, stranger = people["owner"], people["stranger"]
    world = _make_live_world(db, owner, monkeypatch)
    response = api_client.post(
        "/api/trading/mandate-proposals", json={"terms": _terms(world), "reason": "steal"}, headers=auth_headers(stranger)
    )
    assert response.status_code == 400
    assert db.query(TradingMandateProposal).count() == 0


def test_without_migration_0036_and_flag_off_nothing_touches_the_new_table(api_client, db, people, monkeypatch):
    """Deploying this code before the migration runs is safe: with the flag
    off (default) no code path reads or writes trading_mandate_proposals."""
    owner, admin = people["owner"], people["admin_a"]
    world = _make_live_world(db, owner, monkeypatch)
    db.execute(text("DROP TABLE trading_mandate_proposals"))
    db.commit()
    from tests.security.test_live_trading_foundation import FakeGateway

    gateway = FakeGateway()
    preview = control_plane.preview_order(db, owner.id, mandate_id=world["mandate"].id, symbol="BTCUSDT", side="buy", quantity="0.5", gateway=gateway)
    order = control_plane.confirm_order(db, owner.id, order_intent_id=preview["intent"].id, confirmation=preview["confirmation"], gateway=gateway)
    control_plane.sync_order_status(db, order, gateway=gateway)
    control_plane.cancel_order(db, owner.id, order.client_order_id, gateway=gateway)
    control_plane.pause_mandate(db, owner.id, world["mandate"].id, reason="x")
    for path in ("/api/trading/mandates", "/api/trading/orders", "/api/trading/ledger", "/api/trading/reconciliation", "/api/trading/safety-status"):
        assert api_client.get(path, headers=auth_headers(owner)).status_code == 200, path
    for path in ("/admin/trading/kill-switches", "/admin/trading/live-approvals", "/admin/trading/reconciliations", "/admin/trading/audit"):
        assert api_client.get(path, headers=auth_headers(admin)).status_code == 200, path
    assert api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": True, "reason": "drill"}, headers=auth_headers(admin)).status_code == 200
    gone = api_client.get("/api/trading/mandate-proposals", headers=auth_headers(owner))
    assert gone.status_code == 404 and gone.json()["detail"]["code"] == "MANDATE_PROPOSALS_DISABLED"
    db.execute(text("CREATE TABLE trading_mandate_proposals (id VARCHAR PRIMARY KEY)"))  # let teardown drop it
    db.commit()
