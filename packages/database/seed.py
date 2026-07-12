from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.billing.plans import PLANS
from packages.database.models import Asset, SubscriptionPlan, TradingAccount, User, UserPreference


ASSETS = [
    ("BTC", "Bitcoin", "crypto"),
    ("ETH", "Ethereum", "crypto"),
    ("SOL", "Solana", "crypto"),
    ("HYPE", "Hyperliquid", "crypto"),
    ("MSTR", "MicroStrategy", "equity_proxy"),
    ("STRC", "Strategy Credit", "credit_proxy"),
]


def seed_plans(db: Session) -> None:
    settings = get_settings()
    price_ids = settings.stripe_price_by_plan
    for plan in PLANS.values():
        row = db.get(SubscriptionPlan, plan.name) or SubscriptionPlan(name=plan.name)
        row.monthly_price = plan.monthly_price
        row.monthly_credits = plan.monthly_credits
        row.max_daily_reports = plan.max_daily_reports
        row.max_alerts = plan.max_alerts
        row.allowed_data_sources = list(plan.allowed_data_sources)
        row.stripe_price_id = price_ids.get(plan.name)
        row.is_active = True
        db.merge(row)


def seed_assets(db: Session) -> None:
    for symbol, name, category in ASSETS:
        db.merge(Asset(symbol=symbol, name=name, category=category, is_active=True))


def seed_demo_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "demo@puregamma.ai").one_or_none()
    if not user:
        user = User(email="demo@puregamma.ai", name="Demo User", role="admin", plan="Free", credit_balance=30)
        db.add(user)
        db.flush()
    if not user.preference:
        db.add(
            UserPreference(
                user_id=user.id,
                email_recipient=user.email,
                telegram_chat_id="mock-telegram-chat",
                slack_webhook_url="mock-slack-webhook",
                imessage_recipient="+15555550100",
                notification_channels=["email", "telegram", "slack", "imessage"],
            )
        )
    return user


def seed_paper_account(db: Session, user: User) -> TradingAccount:
    account = db.query(TradingAccount).filter_by(user_id=user.id, venue="MOCK", account_type="PAPER").one_or_none()
    if not account:
        account = TradingAccount(user_id=user.id, name="PureGamma Paper", venue="MOCK", account_type="PAPER", base_currency="USD", status="ACTIVE", permissions_json={"paper_order": True, "shadow_order": True, "live_order": False, "withdraw": False, "transfer": False})
        db.add(account)
    return account


def seed_all(db: Session) -> User:
    seed_plans(db)
    seed_assets(db)
    user = seed_demo_user(db)
    seed_paper_account(db, user)
    db.commit()
    from apps.api.services.data_source_service import seed_data_sources
    seed_data_sources(db)
    return user
