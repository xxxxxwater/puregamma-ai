from __future__ import annotations

from pathlib import Path

from apps.api.services.credit_service import consume_credits, quote_task, reserve_task
from packages.database.models import CreditLedger, CreditRefundEvent, CreditRewardGrant
from tests.conftest import auth_headers


def test_admin_router_is_available_during_initial_launch() -> None:
    source = (Path(__file__).resolve().parents[2] / "apps/api/main.py").read_text()
    assert source.index("app.include_router(admin.router)") < source.index("if not settings.initial_launch_mode:")


def test_admin_credit_accounts_are_database_backed_and_role_gated(api_client, normal_user, admin_user):
    denied = api_client.get("/admin/billing/accounts", headers=auth_headers(normal_user))
    response = api_client.get(
        "/admin/billing/accounts",
        params={"search": normal_user.email},
        headers=auth_headers(admin_user),
    )

    assert denied.status_code == 403
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["accounts"][0]["id"] == normal_user.id
    assert response.json()["accounts"][0]["credit_balance"] == normal_user.credit_balance


def test_admin_credit_grant_is_idempotent_and_audited(api_client, db, normal_user, admin_user, user_factory):
    other_user = user_factory("other-credit-user@puregamma.ai", credit_balance=30)
    payload = {
        "credits": 125,
        "reason": "Public beta support adjustment",
        "reference": "PG-ADMIN-1001",
        "idempotency_key": "admin-console-grant-1001",
    }
    denied = api_client.post(
        f"/admin/billing/accounts/{normal_user.id}/credits/grant",
        json=payload,
        headers=auth_headers(normal_user),
    )
    first = api_client.post(
        f"/admin/billing/accounts/{normal_user.id}/credits/grant",
        json=payload,
        headers=auth_headers(admin_user),
    )
    second = api_client.post(
        f"/admin/billing/accounts/{normal_user.id}/credits/grant",
        json=payload,
        headers=auth_headers(admin_user),
    )
    cross_user_replay = api_client.post(
        f"/admin/billing/accounts/{other_user.id}/credits/grant",
        json=payload,
        headers=auth_headers(admin_user),
    )
    db.refresh(normal_user)

    assert denied.status_code == 403
    assert first.status_code == 200
    assert second.status_code == 200
    assert cross_user_replay.status_code == 400
    assert first.json()["grant"]["id"] == second.json()["grant"]["id"]
    assert normal_user.credit_balance == 155
    reward = db.query(CreditRewardGrant).filter_by(idempotency_key=payload["idempotency_key"]).one()
    ledger = db.get(CreditLedger, reward.ledger_entry_id)
    assert reward.granted_by_user_id == admin_user.id
    assert ledger.metadata_json["reason"] == payload["reason"]
    assert ledger.metadata_json["reference"] == payload["reference"]


def test_admin_can_refund_open_reservation_once(api_client, db, normal_user, admin_user):
    starting_balance = normal_user.credit_balance
    quote = quote_task(task_type="default_chat")
    reservation = reserve_task(db, normal_user.id, quote, "admin-refund-open-reservation")
    db.commit()
    payload = {"reason": "Provider did not start", "reference": "PG-REFUND-1001"}

    # The persisted reservation ID is intentionally server-owned and never supplied by the user.
    from packages.database.models import CreditReservationRecord
    row = db.query(CreditReservationRecord).filter_by(idempotency_key=reservation.idempotency_key).one()
    bypass = api_client.post(
        f"/admin/billing/ledger/{row.ledger_entry_id}/refund",
        json=payload,
        headers=auth_headers(admin_user),
    )
    first = api_client.post(
        f"/admin/billing/reservations/{row.id}/refund",
        json=payload,
        headers=auth_headers(admin_user),
    )
    second = api_client.post(
        f"/admin/billing/reservations/{row.id}/refund",
        json=payload,
        headers=auth_headers(admin_user),
    )
    db.refresh(normal_user)

    assert bypass.status_code == 409
    assert first.status_code == 200
    assert second.status_code == 200
    assert normal_user.credit_balance == starting_balance
    assert db.query(CreditRefundEvent).filter_by(reservation_id=row.id).count() == 1


def test_admin_debit_refund_is_idempotent_and_reconciles(api_client, db, normal_user, admin_user):
    debit = consume_credits(
        db,
        normal_user.id,
        "support_refundable_usage",
        7,
        idempotency_key="support-refundable-usage-1",
    )
    db.commit()
    payload = {"reason": "Service quality refund", "reference": "PG-REFUND-1002"}

    first = api_client.post(
        f"/admin/billing/ledger/{debit.id}/refund",
        json=payload,
        headers=auth_headers(admin_user),
    )
    second = api_client.post(
        f"/admin/billing/ledger/{debit.id}/refund",
        json=payload,
        headers=auth_headers(admin_user),
    )
    detail = api_client.get(
        f"/admin/billing/accounts/{normal_user.id}",
        headers=auth_headers(admin_user),
    )
    db.refresh(normal_user)

    assert first.status_code == 200
    assert second.status_code == 200
    assert normal_user.credit_balance == 30
    assert db.query(CreditLedger).filter_by(idempotency_key=f"admin-ledger-refund:{debit.id}").count() == 1
    assert detail.status_code == 200
    assert detail.json()["reconciliation"]["matches"] is True
    refunded_debit = next(row for row in detail.json()["ledger"] if row["id"] == debit.id)
    assert refunded_debit["refundable"] is False
