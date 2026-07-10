from __future__ import annotations

import pytest

from apps.api.services.billing_service import get_credits
from apps.api.services.credit_service import InsufficientCreditsError, consume_credits, grant_credits, refund_credits
from packages.database.models import CreditLedger


def test_free_user_initial_credits(demo_user):
    assert demo_user.plan == "Free"
    assert demo_user.credit_balance == 30


def test_consume_credits_writes_ledger_balance(db, demo_user):
    entry = consume_credits(db, demo_user.id, "daily_market_report", 10, {"request_id": "req-1"})
    db.commit()
    db.refresh(demo_user)

    assert demo_user.credit_balance == 20
    assert entry.credits_delta == -10
    assert entry.balance_after == 20
    assert entry.metadata_json["request_id"] == "req-1"


def test_insufficient_credits_raises_without_mutating_balance(db, demo_user):
    with pytest.raises(InsufficientCreditsError):
        consume_credits(db, demo_user.id, "backtest", 1000)

    db.rollback()
    db.refresh(demo_user)
    assert demo_user.credit_balance == 30
    assert db.query(CreditLedger).filter(CreditLedger.user_id == demo_user.id).count() == 0


def test_refund_credits_restores_balance_and_ledger(db, demo_user):
    consume_credits(db, demo_user.id, "telegram_alert", 1)
    refund = refund_credits(db, demo_user.id, "telegram_alert", 1, {"reason": "provider_failure"})
    db.commit()
    db.refresh(demo_user)

    assert demo_user.credit_balance == 30
    assert refund.action == "telegram_alert_refund"
    assert refund.credits_delta == 1
    assert refund.balance_after == 30


def test_monthly_grant_balance_matches_ledger_sum(db, demo_user):
    grant_credits(db, demo_user.id, "monthly_credit_grant", 1000, {"plan": "Pro"})
    consume_credits(db, demo_user.id, "daily_market_report", 10)
    refund_credits(db, demo_user.id, "daily_market_report", 10)
    db.commit()

    credits = get_credits(db, demo_user.id)
    ledger_total = sum(item["credits_delta"] for item in credits["usage_history"])

    assert credits["credit_balance"] == 1030
    assert demo_user.credit_balance == 30 + ledger_total


@pytest.mark.parametrize("operation", [consume_credits, grant_credits, refund_credits])
def test_negative_credit_amount_rejected(operation, db, demo_user):
    with pytest.raises(ValueError):
        operation(db, demo_user.id, "bad_delta", -1)
