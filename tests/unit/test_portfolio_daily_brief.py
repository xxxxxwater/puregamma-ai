from datetime import datetime, timezone

from apps.api.services.daily_brief_service import gather_context, generate_daily_brief
from apps.api.services.report_service import create_daily_report
from packages.database.models import AccountSnapshot, CreditLedger, PositionSnapshot, TradingAccount


def _portfolio(db, user):
    account = TradingAccount(user_id=user.id, name="Read-only account", venue="HYPERLIQUID", account_type="READ_ONLY", status="ACTIVE")
    db.add(account)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(AccountSnapshot(user_id=user.id, account_id=account.id, balance=100_000, equity=100_000, available_margin=20_000, daily_pnl=1_250, drawdown=0.02, exposure=80_000, stale=False, captured_at=now))
    db.add_all([
        PositionSnapshot(user_id=user.id, account_id=account.id, instrument="BTC", quantity=0.6, side="LONG", average_price=90_000, mark_price=100_000, raw_event_reference={"value": 60_000}, captured_at=now),
        PositionSnapshot(user_id=user.id, account_id=account.id, instrument="ETH", quantity=10, side="LONG", average_price=3_000, mark_price=4_000, raw_event_reference={"value": 40_000}, captured_at=now),
    ])
    user.preference.include_portfolio_in_ai = False
    db.commit()


def test_daily_brief_uses_tenant_portfolio_without_sending_it_to_llm(db, pro_user):
    _portfolio(db, pro_user)

    context = gather_context(db, pro_user.id, "en")
    brief = generate_daily_brief(db, pro_user.id, "en")

    assert context["portfolio"]["total_nav"] == 100_000
    assert context["portfolio"]["top_holdings"][0]["symbol"] == "BTC"
    assert context["portfolio_shared_with_llm"] is False
    assert "NAV: $100,000.00" in brief
    assert "BTC 60.0%" in brief


def test_daily_report_is_idempotent_for_user_date_and_language(db, pro_user):
    _portfolio(db, pro_user)
    initial_balance = pro_user.credit_balance

    first = create_daily_report(db, pro_user.id, "en")
    second = create_daily_report(db, pro_user.id, "en")

    db.refresh(pro_user)
    assert first.id == second.id
    assert pro_user.credit_balance == initial_balance - 10
    assert db.query(CreditLedger).filter(CreditLedger.idempotency_key.like("report-charge:%")).count() == 1
