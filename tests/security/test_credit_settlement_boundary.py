from types import SimpleNamespace

import pytest

from apps.api.dependencies import create_access_token
from apps.api.services import agent_service, backtest_service
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from packages.database.models import (
    CreditRefundEvent,
    CreditReservationRecord,
    CreditSettlementRecord,
)


def test_regular_user_cannot_submit_actual_usage(api_client, normal_user):
    headers = {"Authorization": f"Bearer {create_access_token(normal_user)}"}

    reservation = api_client.post(
        "/billing/reservations",
        json={"task_type": "default_chat", "idempotency_key": "forged-reservation"},
        headers=headers,
    )
    settlement = api_client.post(
        "/billing/settlements/forged-reservation",
        json={"actual_credits": 0, "idempotency_key": "forged-settlement"},
        headers=headers,
    )

    assert reservation.status_code == 404
    assert settlement.status_code == 404


def test_persisted_settlement_is_terminal_and_idempotent(db, normal_user):
    starting_balance = normal_user.credit_balance
    quote = quote_task(task_type="default_chat", input_tokens=10)
    reservation = reserve_task(db, normal_user.id, quote, "state-machine-reservation")
    db.commit()

    first = settle_task(db, normal_user.id, reservation, 1, metadata={"source": "server_usage"})
    second = settle_task(db, normal_user.id, reservation, 0, metadata={"source": "forged_retry"})
    db.commit()
    db.refresh(normal_user)

    assert first == second
    assert normal_user.credit_balance == starting_balance - first.actual
    assert db.query(CreditReservationRecord).filter_by(idempotency_key="state-machine-reservation", status="SETTLED").count() == 1
    assert db.query(CreditSettlementRecord).count() == 1
    with pytest.raises(ValueError, match="Settled reservation"):
        refund_task(db, normal_user.id, reservation, "INVALID_LATE_REFUND")


def test_full_refund_is_terminal_and_idempotent(db, normal_user):
    starting_balance = normal_user.credit_balance
    quote = quote_task(task_type="default_chat")
    reservation = reserve_task(db, normal_user.id, quote, "refund-state-reservation")
    db.commit()

    first = refund_task(db, normal_user.id, reservation, "PROVIDER_FAILED")
    second = refund_task(db, normal_user.id, reservation, "RETRY_PROVIDER_FAILED")
    db.commit()
    db.refresh(normal_user)

    assert first == second
    assert normal_user.credit_balance == starting_balance
    assert db.query(CreditRefundEvent).count() == 1


def test_pending_agent_cancel_refunds_persisted_reservation(api_client, db, normal_user):
    headers = {"Authorization": f"Bearer {create_access_token(normal_user)}"}
    conversation = agent_service.create_conversation(db, normal_user)
    run = agent_service.start_run(db, normal_user, conversation, "Cancel before execution")
    balance_after_reservation = normal_user.credit_balance

    response = api_client.post(f"/api/agent/runs/{run.id}/cancel", headers=headers)
    db.refresh(normal_user)

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert normal_user.credit_balance > balance_after_reservation
    assert db.query(CreditReservationRecord).filter_by(idempotency_key=f"agent-charge:{run.id}", status="REFUNDED").count() == 1


def test_production_rejects_mock_backtest_before_charging(db, max_user, monkeypatch):
    starting_balance = max_user.credit_balance
    monkeypatch.setattr(
        backtest_service,
        "get_settings",
        lambda: SimpleNamespace(app_environment="production"),
    )

    with pytest.raises(ValueError, match="MOCK_BACKTEST_DISABLED_IN_PRODUCTION"):
        backtest_service.run_backtest(db, max_user.id, "BTC momentum", "BTC", engine="mock")

    db.refresh(max_user)
    assert max_user.credit_balance == starting_balance
