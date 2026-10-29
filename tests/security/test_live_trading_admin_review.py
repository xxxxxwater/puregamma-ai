"""Administrator review of the LIVE control plane.

Pins: every admin trading route is authorized on the server (a normal user
gets 403, an anonymous caller 401, whatever the browser shows), every change
writes an admin audit row with the reason, kill-switch input is validated and
a release that matches nothing is a 404, and reviewing a reconciliation never
edits it or resumes the paused mandate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from packages.database.models import LiveUserApproval, TradingAuditLog, TradingKillSwitch, TradingReconciliation
from packages.live_trading import admin_review, control_plane, kill_switch
from tests.conftest import auth_headers
from tests.security.test_live_trading_foundation import FakeGateway, _make_fill_order, _make_live_world

ADMIN_ROUTES = [
    ("get", "/admin/trading/kill-switches", None),
    ("post", "/admin/trading/kill-switch", {"scope": "global", "active": True, "reason": "drill"}),
    ("get", "/admin/trading/live-approvals", None),
    ("post", "/admin/trading/live-approvals", {"user_id": "x", "approve": True, "max_total_notional": "1", "notes": "ok"}),
    ("get", "/admin/trading/reconciliations?exceptions_only=true", None),
    ("post", "/admin/trading/reconciliations/r1/review", {"note": "looked"}),
    ("get", "/admin/trading/audit", None),
    ("get", "/admin/trading/ledger", None),
]


def _call(api_client, method, path, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(api_client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_a_normal_user_is_refused_by_the_server(api_client, db, normal_user, method, path, body):
    response = _call(api_client, method, path, body, auth_headers(normal_user))
    assert response.status_code == 403, response.text
    assert db.query(TradingKillSwitch).count() == 0
    assert db.query(TradingAuditLog).count() == 0
    assert db.query(LiveUserApproval).count() == 0


@pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
def test_an_anonymous_caller_is_refused(api_client, method, path, body):
    assert _call(api_client, method, path, body).status_code == 401


def _admin_events(db, action):
    return db.query(TradingAuditLog).filter_by(action=action, actor_type="admin").all()


def test_engage_and_release_require_a_reason_and_are_audited(api_client, db, admin_user):
    headers = auth_headers(admin_user)
    missing = api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": True, "reason": ""}, headers=headers)
    assert missing.status_code == 422
    blank = api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": True, "reason": "   "}, headers=headers)
    assert blank.status_code == 400

    engaged = api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": True, "reason": "exchange incident"}, headers=headers)
    assert engaged.status_code == 200
    listing = api_client.get("/admin/trading/kill-switches", headers=headers).json()
    assert [row["reason"] for row in listing["active"]] == ["exchange incident"]

    released = api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": False, "reason": "incident closed"}, headers=headers)
    assert released.status_code == 200
    listing = api_client.get("/admin/trading/kill-switches", headers=headers).json()
    assert listing["active"] == [] and listing["released"][0]["resolved_by"] == admin_user.id

    [on] = _admin_events(db, admin_review.KILL_SWITCH_ENGAGED)
    [off] = _admin_events(db, admin_review.KILL_SWITCH_RELEASED)
    assert on.request_json == {"admin_user_id": admin_user.id, "scope": "global", "scope_id": None, "reason": "exchange incident"}
    assert off.request_json["reason"] == "incident closed"
    audit = api_client.get("/admin/trading/audit", headers=headers).json()["events"]
    assert {event["action"] for event in audit} == {admin_review.KILL_SWITCH_ENGAGED, admin_review.KILL_SWITCH_RELEASED}


def test_releasing_a_switch_that_is_not_active_is_a_404(api_client, db, admin_user, user_factory):
    target = user_factory("ks-target@test.com")
    other = user_factory("ks-other@test.com")
    headers = auth_headers(admin_user)
    assert api_client.post("/admin/trading/kill-switch", json={"scope": "user", "scope_id": target.id, "active": True, "reason": "fraud review"}, headers=headers).status_code == 200
    # An active switch for another id in the same scope must not read as a release.
    wrong = api_client.post("/admin/trading/kill-switch", json={"scope": "user", "scope_id": other.id, "active": False, "reason": "typo"}, headers=headers)
    assert wrong.status_code == 404
    assert kill_switch.is_engaged(db, "user", target.id)
    assert _admin_events(db, admin_review.KILL_SWITCH_RELEASED) == []


@pytest.mark.parametrize(
    "body,status",
    [
        ({"scope": "global", "scope_id": "x", "active": True, "reason": "r"}, 400),
        ({"scope": "user", "active": True, "reason": "r"}, 400),
        ({"scope": "user", "scope_id": "no-such-user", "active": True, "reason": "r"}, 404),
        ({"scope": "mandate", "scope_id": "no-such-mandate", "active": True, "reason": "r"}, 404),
        ({"scope": "connection", "scope_id": "no-such-connection", "active": True, "reason": "r"}, 404),
        ({"scope": "everything", "active": True, "reason": "r"}, 422),
    ],
)
def test_kill_switch_targets_are_validated(api_client, db, admin_user, body, status):
    response = api_client.post("/admin/trading/kill-switch", json=body, headers=auth_headers(admin_user))
    assert response.status_code == status, response.text
    assert db.query(TradingKillSwitch).count() == 0


def test_a_mandate_kill_switch_pauses_and_its_release_does_not_resume(api_client, db, admin_user, user_factory, monkeypatch):
    owner = user_factory("ks-mandate@test.com")
    world = _make_live_world(db, owner, monkeypatch)
    mandate = world["mandate"]
    headers = auth_headers(admin_user)
    api_client.post("/admin/trading/kill-switch", json={"scope": "mandate", "scope_id": mandate.id, "active": True, "reason": "limit breach"}, headers=headers)
    db.refresh(mandate)
    assert mandate.paused and mandate.kill_switch_state == "active"
    [event] = _admin_events(db, admin_review.KILL_SWITCH_ENGAGED)
    assert event.user_id == owner.id

    api_client.post("/admin/trading/kill-switch", json={"scope": "mandate", "scope_id": mandate.id, "active": False, "reason": "reviewed"}, headers=headers)
    db.refresh(mandate)
    assert mandate.kill_switch_state == "inactive"
    assert mandate.paused  # resuming stays the owner's explicit, re-gated action


def test_cancel_still_works_while_the_admin_kill_switch_is_engaged(api_client, db, admin_user, user_factory, monkeypatch):
    owner = user_factory("ks-cancel@test.com")
    world = _make_live_world(db, owner, monkeypatch)
    order = _make_fill_order(db, owner, world, side="buy", quantity="0.5")
    api_client.post("/admin/trading/kill-switch", json={"scope": "global", "active": True, "reason": "halt"}, headers=auth_headers(admin_user))
    canceled = control_plane.cancel_order(db, owner.id, order.client_order_id, gateway=FakeGateway())
    assert canceled.status == "canceled"


def test_live_approval_requires_a_reason_is_audited_and_never_self_approved(api_client, db, admin_user, user_factory):
    target = user_factory("approve-me@test.com")
    headers = auth_headers(admin_user)
    no_reason = api_client.post("/admin/trading/live-approvals", json={"user_id": target.id, "approve": True, "max_total_notional": "1000"}, headers=headers)
    assert no_reason.status_code == 422

    ok = api_client.post("/admin/trading/live-approvals", json={"user_id": target.id, "approve": True, "max_total_notional": "1000.5", "notes": "KYC verified"}, headers=headers)
    assert ok.status_code == 200
    approval = ok.json()["approval"]
    assert approval["status"] == "approved" and approval["max_total_notional"] == "1000.50000000"
    assert approval["reviewed_by"] == admin_user.id
    [event] = _admin_events(db, admin_review.LIVE_APPROVAL_SET)
    assert event.user_id == target.id and event.request_json["reason"] == "KYC verified"
    assert event.result_json["previous_status"] == "none"

    listed = api_client.get("/admin/trading/live-approvals", headers=headers).json()["approvals"]
    assert [(row["email"], row["status"]) for row in listed] == [("approve-me@test.com", "approved")]

    own = api_client.post("/admin/trading/live-approvals", json={"user_id": admin_user.id, "approve": True, "max_total_notional": "1", "notes": "me"}, headers=headers)
    assert own.status_code == 403
    assert db.query(LiveUserApproval).filter_by(user_id=admin_user.id).count() == 0

    rejected = api_client.post("/admin/trading/live-approvals", json={"user_id": target.id, "approve": False, "max_total_notional": "0", "notes": "risk review"}, headers=headers)
    assert rejected.json()["approval"]["status"] == "rejected" and rejected.json()["approval"]["revoked_at"]


def test_reviewing_a_reconciliation_appends_an_audit_row_only(api_client, db, admin_user, user_factory, monkeypatch):
    owner = user_factory("recon-review@test.com")
    world = _make_live_world(db, owner, monkeypatch)
    mandate = world["mandate"]
    mandate.paused = True
    mandate.pause_reason = "reconciliation_discrepancy"
    row = TradingReconciliation(
        user_id=owner.id, account_id=world["account"].id, mandate_id=mandate.id, status="discrepancy",
        exchange_balance_json={"cash": "10"}, ledger_balance_json={"cash": "0E-8"}, nav_json={},
        differences_json=[{"source": "exchange_vs_ledger", "delta": "10"}], actions_json=["mandate_paused"], trace_id="tr",
    )
    ok_row = TradingReconciliation(
        user_id=owner.id, account_id=world["account"].id, status="ok", trace_id="tr2",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add_all([row, ok_row])
    db.commit()
    headers = auth_headers(admin_user)

    pending = api_client.get("/admin/trading/reconciliations?exceptions_only=true&unreviewed_only=true", headers=headers).json()["reconciliations"]
    assert [item["id"] for item in pending] == [row.id]
    assert pending[0]["ledger_balance"] == {"cash": "0.00000000"}

    assert api_client.post(f"/admin/trading/reconciliations/{row.id}/review", json={"note": ""}, headers=headers).status_code == 422
    assert api_client.post("/admin/trading/reconciliations/missing/review", json={"note": "x"}, headers=headers).status_code == 404
    reviewed = api_client.post(f"/admin/trading/reconciliations/{row.id}/review", json={"note": "exchange deposit not yet booked"}, headers=headers)
    assert reviewed.status_code == 200
    assert reviewed.json()["reconciliation"]["reviewed"]["note"] == "exchange deposit not yet booked"
    assert reviewed.json()["reconciliation"]["reviewed"]["reviewed_by"] == admin_user.id

    db.expire_all()
    assert db.get(TradingReconciliation, row.id).status == "discrepancy"
    assert db.get(type(mandate), mandate.id).paused is True
    assert api_client.get("/admin/trading/reconciliations?unreviewed_only=true&exceptions_only=true", headers=headers).json()["reconciliations"] == []

    # The owner sees that it was reviewed, but not the administrator's note.
    view = api_client.get(f"/api/trading/reconciliation?account_id={world['account'].id}", headers=auth_headers(owner)).json()
    assert view["latest"]["id"] == row.id
    assert view["latest"]["reviewed"]["status"] == "REVIEWED"
    assert "note" not in view["latest"]["reviewed"] and "reviewed_by" not in view["latest"]["reviewed"]
    assert [item["reviewed"] for item in view["history"]] == [True, False]


def test_unreviewed_only_is_filtered_before_the_limit(api_client, db, admin_user, user_factory, monkeypatch):
    """A reviewed, newer exception must not push an older unreviewed one out
    of a limited page."""
    owner = user_factory("recon-limit@test.com")
    world = _make_live_world(db, owner, monkeypatch)
    now = datetime.now(timezone.utc)
    old = TradingReconciliation(user_id=owner.id, account_id=world["account"].id, status="discrepancy", trace_id="old", created_at=now - timedelta(hours=2))
    new = TradingReconciliation(user_id=owner.id, account_id=world["account"].id, status="discrepancy", trace_id="new", created_at=now)
    db.add_all([old, new])
    db.commit()
    admin_review.review_reconciliation(db, admin_user, new.id, note="seen")

    assert [item["id"] for item in admin_review.list_reconciliations(db, exceptions_only=True, unreviewed_only=True, limit=1)] == [old.id]
    assert [item["id"] for item in admin_review.list_reconciliations(db, exceptions_only=True, limit=1)] == [new.id]
