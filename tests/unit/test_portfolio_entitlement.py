import pytest

from apps.api.services.billing_service import mock_upgrade, process_stripe_event
from apps.api.services.portfolio_service import connect_hyperliquid
from packages.database.models import TradingAccount
from tests.conftest import stripe_event


def test_free_user_can_add_one_portfolio_but_not_two(db, normal_user):
    connect_hyperliquid(db, normal_user, "0x" + "1" * 40)
    with pytest.raises(PermissionError, match="PORTFOLIO_LIMIT_REACHED"):
        connect_hyperliquid(db, normal_user, "0x" + "2" * 40)


def test_pro_user_cannot_exceed_one_portfolio(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    connect_hyperliquid(db, demo_user, "0x" + "1" * 40)

    with pytest.raises(PermissionError, match="PORTFOLIO_LIMIT_REACHED"):
        connect_hyperliquid(db, demo_user, "0x" + "2" * 40)


def test_past_due_user_keeps_existing_portfolio_read_only_but_cannot_add(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    existing = connect_hyperliquid(db, demo_user, "0x" + "1" * 40)
    event, raw = stripe_event("evt-portfolio-past-due", "invoice.payment_failed", {"customer": demo_user.stripe_customer_id})
    process_stripe_event(db, event, raw)

    assert db.get(TradingAccount, existing.id) is not None
    with pytest.raises(PermissionError, match="PORTFOLIO_ACCESS_RESTRICTED"):
        connect_hyperliquid(db, demo_user, "0x" + "2" * 40)
