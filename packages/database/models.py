from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=new_id)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False, default="PureGamma User")
    role = Column(String, nullable=False, default="user")
    plan = Column(String, nullable=False, default="Free")
    credit_balance = Column(Integer, nullable=False, default=30)
    stripe_customer_id = Column(String, nullable=True, index=True)
    google_user_id = Column(String, nullable=True, unique=True, index=True)
    avatar_url = Column(String, nullable=True)
    auth_provider = Column(String, nullable=False, default="mock")
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    session_version = Column(Integer, nullable=False, default=0)

    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user")
    identities = relationship("UserIdentity", back_populates="user", cascade="all, delete-orphan")


class UserIdentity(Base, TimestampMixin):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    provider_subject = Column(String, nullable=False)
    provider_email = Column(String, nullable=True, index=True)
    provider_email_verified = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="identities")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    preferred_assets = Column(JSON, default=lambda: ["BTC", "ETH", "SOL", "HYPE", "MSTR", "STRC"], nullable=False)
    risk_level = Column(String, nullable=False, default="balanced")
    preferred_style = Column(String, nullable=False, default="concise")
    locale = Column(String, nullable=False, default="en")
    excluded_assets = Column(JSON, default=list, nullable=False)
    notification_channels = Column(JSON, default=lambda: ["email"], nullable=False)
    subscription_cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    subscription_cancel_at = Column(DateTime(timezone=True), nullable=True)
    imessage_recipient = Column(String, nullable=True)
    imessage_recipient_verified_at = Column(DateTime(timezone=True), nullable=True)
    telegram_chat_id = Column(String, nullable=True)
    slack_webhook_url = Column(String, nullable=True)
    email_recipient = Column(String, nullable=True)
    portfolio_autopilot_json = Column(JSON, default=dict, nullable=False)
    include_portfolio_in_ai = Column(Boolean, nullable=False, default=True)

    user = relationship("User", back_populates="preference")


class DailyBriefPreference(Base, TimestampMixin):
    __tablename__ = "daily_brief_preferences"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False, index=True)
    timezone = Column(String, nullable=False, default="UTC")
    local_time = Column(String, nullable=False, default="08:30")
    channel = Column(String, nullable=False, default="email", index=True)
    locale = Column(String, nullable=False, default="en")
    include_portfolio = Column(Boolean, nullable=False, default=True)
    include_market = Column(Boolean, nullable=False, default=True)
    include_signals = Column(Boolean, nullable=False, default=True)
    include_risk = Column(Boolean, nullable=False, default=True)
    include_sentiment = Column(Boolean, nullable=False, default=False)
    quiet_hours = Column(JSON, default=dict, nullable=False)
    max_length = Column(Integer, nullable=False, default=3000)
    next_delivery_at = Column(DateTime(timezone=True), nullable=True, index=True)
    recipient = Column(String, nullable=True)
    recipient_verified_at = Column(DateTime(timezone=True), nullable=True)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    stripe_subscription_id = Column(String, nullable=True, unique=True, index=True)
    stripe_customer_id = Column(String, nullable=True, index=True)
    stripe_price_id = Column(String, nullable=True)
    plan_name = Column(String, nullable=False, default="Free")
    status = Column(String, nullable=False, default="inactive")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="subscriptions")


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    name = Column(String, primary_key=True)
    monthly_price = Column(Float, nullable=True)
    monthly_credits = Column(Integer, nullable=False)
    max_daily_reports = Column(Integer, nullable=False)
    max_alerts = Column(Integer, nullable=False)
    allowed_data_sources = Column(JSON, default=list, nullable=False)
    stripe_price_id = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    credits_delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    id = Column(String, primary_key=True, default=new_id)
    stripe_event_id = Column(String, nullable=False, unique=True, index=True)
    event_type = Column(String, nullable=False)
    processed = Column(Boolean, nullable=False, default=False)
    requires_manual_review = Column(Boolean, nullable=False, default=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    raw_payload_hash = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BillingCheckoutIntent(Base):
    __tablename__ = "billing_checkout_intents"
    __table_args__ = (UniqueConstraint("public_reference", name="uq_billing_checkout_public_reference"),)

    id = Column(String, primary_key=True, default=new_id)
    public_reference = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    plan_name = Column(String, nullable=False)
    checkout_mode = Column(String, nullable=False)
    stripe_payment_link_url = Column(Text, nullable=True)
    stripe_checkout_session_id = Column(String, nullable=True, index=True)
    stripe_customer_id = Column(String, nullable=True, index=True)
    stripe_price_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created", index=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False)
    task_type = Column(String, nullable=False, index=True)
    locale = Column(String, nullable=False, default="en", index=True)
    prompt_summary = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="success", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Asset(Base):
    __tablename__ = "assets"

    symbol = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    asset_id = Column(String, ForeignKey("assets.symbol"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, nullable=False)
    market_cap = Column(Float, nullable=True)
    funding_rate = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class SharedMarketIntelligence(Base):
    __tablename__ = "shared_market_intelligence"

    id = Column(String, primary_key=True, default=new_id)
    market_regime = Column(String, nullable=False)
    summary_markdown = Column(Text, nullable=False)
    assets = Column(JSON, default=list, nullable=False)
    source_snapshot_ids = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(String, primary_key=True, default=new_id)
    asset = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    risk_score = Column(Integer, nullable=False)
    thesis = Column(Text, nullable=False)
    catalyst = Column(Text, nullable=False)
    invalidation = Column(Text, nullable=False)
    timeframe = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    report_type = Column(String, nullable=False)
    language = Column(String, nullable=False, default="en", index=True)
    content_markdown = Column(Text, nullable=False)
    assets = Column(JSON, default=list, nullable=False)
    source_intelligence_id = Column(String, ForeignKey("shared_market_intelligence.id"), nullable=True)
    report_date = Column(Date, nullable=True, index=True)
    status = Column(String, nullable=False, default="completed", index=True)
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    asset = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String, nullable=False, default="medium")
    channel = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    idempotency_key = Column(String, nullable=False, unique=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_notification_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    recipient = Column(String, nullable=True)
    payload = Column(JSON, default=dict, nullable=False)
    locale = Column(String, nullable=False, default="en", index=True)
    status = Column(String, nullable=False, default="pending")
    provider_response = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)


class IMessageVerificationChallenge(Base):
    __tablename__ = "imessage_verification_challenges"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient = Column(String, nullable=False)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    strategy_name = Column(String, nullable=False)
    asset = Column(String, nullable=False)
    params_json = Column(JSON, default=dict, nullable=False)
    result_json = Column(JSON, default=dict, nullable=False)
    credits_spent = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default="NOT_CONNECTED", index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    item_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, default=dict, nullable=False)


class DataSourceSyncRun(Base):
    __tablename__ = "data_source_sync_runs"
    __table_args__ = (UniqueConstraint("provider_id", "idempotency_key", name="uq_provider_sync_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    provider_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="RUNNING", index=True)
    trace_id = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    fetched_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Source(Base, TimestampMixin):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("provider", "external_key", name="uq_source_provider_external"),)

    id = Column(String, primary_key=True, default=new_id)
    provider = Column(String, nullable=False, index=True)
    provider_type = Column(String, nullable=False, index=True)
    external_key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    source_url = Column(Text, nullable=True)
    language = Column(String, nullable=False, default="en")
    enabled = Column(Boolean, nullable=False, default=True)
    credibility_score = Column(Float, nullable=False, default=0.5)
    source_license = Column(String, nullable=False, default="unknown")
    redistribution_allowed = Column(Boolean, nullable=False, default=False)
    retention_policy = Column(String, nullable=False, default="configured")
    config_json = Column(JSON, default=dict, nullable=False)


class RawDocument(Base):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_raw_provider_external"),
        UniqueConstraint("content_hash", name="uq_raw_content_hash"),
    )

    id = Column(String, primary_key=True, default=new_id)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False)
    cursor = Column(Text, nullable=True)
    content_hash = Column(String, nullable=False, index=True)
    raw_payload = Column(JSON, default=dict, nullable=False)
    source_url = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    license_status = Column(String, nullable=False, default="unknown")
    retention_policy = Column(String, nullable=False, default="configured")
    processing_status = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class NormalizedDocument(Base):
    __tablename__ = "normalized_documents"
    __table_args__ = (UniqueConstraint("stable_hash", name="uq_normalized_stable_hash"),)

    id = Column(String, primary_key=True, default=new_id)
    raw_document_id = Column(String, ForeignKey("raw_documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    source_name = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    url = Column(Text, nullable=True)
    author = Column(String, nullable=True, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    language = Column(String, nullable=False, default="en")
    symbols = Column(JSON, default=list, nullable=False)
    topics = Column(JSON, default=list, nullable=False)
    sentiment = Column(JSON, default=dict, nullable=False)
    credibility_score = Column(Float, nullable=False, default=0.5)
    engagement_metrics = Column(JSON, default=dict, nullable=False)
    raw_payload = Column(JSON, default=dict, nullable=False)
    license_status = Column(String, nullable=False, default="unknown")
    retention_policy = Column(String, nullable=False, default="configured")
    redistribution_allowed = Column(Boolean, nullable=False, default=False)
    stable_hash = Column(String, nullable=False, index=True)
    event_fingerprint = Column(String, nullable=False, index=True)
    final_score = Column(Float, nullable=False, default=0.0, index=True)
    alert_processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (UniqueConstraint("document_id", "symbol", name="uq_document_entity_symbol"),)

    id = Column(String, primary_key=True, default=new_id)
    document_id = Column(String, ForeignKey("normalized_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    mention_text = Column(String, nullable=True)
    relevance_score = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SentimentSignal(Base):
    __tablename__ = "sentiment_signals"

    id = Column(String, primary_key=True, default=new_id)
    document_id = Column(String, ForeignKey("normalized_documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    sentiment_score = Column(Float, nullable=False)
    sentiment_label = Column(String, nullable=False, index=True)
    source_credibility = Column(Float, nullable=False)
    freshness_score = Column(Float, nullable=False)
    engagement_score = Column(Float, nullable=False)
    asset_relevance = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False, index=True)
    event_fingerprint = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProviderSyncLog(Base):
    __tablename__ = "provider_sync_logs"
    __table_args__ = (UniqueConstraint("provider_id", "idempotency_key", name="uq_provider_log_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    provider_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    cursor_before = Column(Text, nullable=True)
    cursor_after = Column(Text, nullable=True)
    fetched_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    http_status = Column(Integer, nullable=True)
    rate_limit_reset_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    usage_json = Column(JSON, default=dict, nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FinTwitAccount(Base, TimestampMixin):
    __tablename__ = "fintwit_accounts"
    __table_args__ = (UniqueConstraint("platform", "username", name="uq_fintwit_platform_username"),)

    id = Column(String, primary_key=True, default=new_id)
    username = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    platform = Column(String, nullable=False, default="x", index=True)
    category = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False, default="en")
    credibility_score = Column(Float, nullable=False, default=0.6)
    account_weight = Column(Float, nullable=False, default=1.0)
    historical_accuracy = Column(Float, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    source_url = Column(Text, nullable=True)
    provider_user_id = Column(String, nullable=True)
    collection_method = Column(String, nullable=False, default="official_api")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_source_external"),
        UniqueConstraint("content_hash", name="uq_news_content_hash"),
    )

    id = Column(String, primary_key=True, default=new_id)
    source = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=False, index=True)
    author = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    content_hash = Column(String, nullable=False)
    language = Column(String, nullable=True)
    sentiment_score = Column(Numeric(8, 6), nullable=True)
    sentiment_label = Column(String, nullable=True)
    related_symbols = Column(JSON, default=list, nullable=False)
    provenance_json = Column(JSON, default=dict, nullable=False)


class MarketQuoteRecord(Base):
    __tablename__ = "market_quotes"
    __table_args__ = (UniqueConstraint("provider", "symbol", "source_timestamp", name="uq_market_quote_source_time"),)

    id = Column(String, primary_key=True, default=new_id)
    symbol = Column(String, nullable=False, index=True)
    base_asset = Column(String, nullable=False)
    quote_asset = Column(String, nullable=False)
    asset_type = Column(String, nullable=False)
    provider = Column(String, nullable=False, index=True)
    price = Column(Numeric(38, 18), nullable=True)
    change_24h_pct = Column(Numeric(20, 10), nullable=True)
    volume_24h_base = Column(Numeric(38, 18), nullable=True)
    volume_24h_quote = Column(Numeric(38, 18), nullable=True)
    high_24h = Column(Numeric(38, 18), nullable=True)
    low_24h = Column(Numeric(38, 18), nullable=True)
    bid = Column(Numeric(38, 18), nullable=True)
    ask = Column(Numeric(38, 18), nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    provenance_json = Column(JSON, default=dict, nullable=False)


class DefiMetric(Base):
    __tablename__ = "defi_metrics"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "chain", "metric_type", name="uq_defi_metric_entity"),)

    id = Column(String, primary_key=True, default=new_id)
    provider = Column(String, nullable=False, default="defillama")
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False, index=True)
    entity_name = Column(String, nullable=False)
    chain = Column(String, nullable=True, index=True)
    metric_type = Column(String, nullable=False, index=True)
    value = Column(Numeric(38, 18), nullable=False)
    currency = Column(String, nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    provenance_json = Column(JSON, default=dict, nullable=False)


class OnchainMetric(Base):
    __tablename__ = "onchain_metrics"
    __table_args__ = (UniqueConstraint("provider", "chain", "entity_id", "metric_type", name="uq_onchain_metric_entity"),)

    id = Column(String, primary_key=True, default=new_id)
    provider = Column(String, nullable=False, index=True)
    chain = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False)
    metric_type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    block_number = Column(Integer, nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    provenance_json = Column(JSON, default=dict, nullable=False)


class AgentConversation(Base, TimestampMixin):
    __tablename__ = "agent_conversations"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False, default="New research")
    summary = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"

    id = Column(String, primary_key=True, default=new_id)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="pending", index=True)
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    context_json = Column(JSON, default=dict, nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=new_id)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False)
    assistant_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    tool_calls_count = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Numeric(20, 10), nullable=False, default=0)
    trace_id = Column(String, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    usage_recorded = Column(Boolean, nullable=False, default=False)
    credit_cost = Column(Integer, nullable=False, default=0)
    credit_refunded = Column(Boolean, nullable=False, default=False)
    queue_priority = Column(Integer, nullable=False, default=0)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id = Column(String, primary_key=True, default=new_id)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String, nullable=False, index=True)
    arguments_json = Column(JSON, default=dict, nullable=False)
    result_summary = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AgentMessageSource(Base):
    __tablename__ = "agent_message_sources"
    __table_args__ = (UniqueConstraint("message_id", "citation_index", name="uq_message_citation_index"),)

    id = Column(String, primary_key=True, default=new_id)
    message_id = Column(String, ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    citation_index = Column(Integer, nullable=False)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_usage_event_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class TradingAccount(Base, TimestampMixin):
    __tablename__ = "trading_accounts"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    venue = Column(String, nullable=False, default="MOCK", index=True)
    account_type = Column(String, nullable=False, default="PAPER")
    base_currency = Column(String, nullable=False, default="USD")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    permissions_json = Column(JSON, default=lambda: {"paper_order": True, "shadow_order": True, "live_order": False, "withdraw": False, "transfer": False}, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class ExchangeConnection(Base, TimestampMixin):
    __tablename__ = "exchange_connections"
    __table_args__ = (UniqueConstraint("user_id", "account_id", "adapter", name="uq_exchange_connection_account_adapter"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    adapter = Column(String, nullable=False)
    environment = Column(String, nullable=False, default="paper")
    credential_reference = Column(String, nullable=True)
    credential_ciphertext = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="DISCONNECTED", index=True)
    last_health_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class TradingStrategy(Base, TimestampMixin):
    __tablename__ = "strategies"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="DRAFT", index=True)
    current_version = Column(Integer, nullable=False, default=1)
    execution_mode = Column(String, nullable=False, default="PAPER")
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    draft_json = Column(JSON, default=dict, nullable=False)
    config_hash = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="DRAFT")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class StrategyIntent(Base, TimestampMixin):
    __tablename__ = "strategy_intents"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_strategy_intent_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    intent_type = Column(String, nullable=False, index=True)
    execution_mode = Column(String, nullable=False)
    payload_json = Column(JSON, default=dict, nullable=False)
    config_hash = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    confirmation_required = Column(Boolean, nullable=False, default=True)
    confirmation_token_hash = Column(String, nullable=True)
    approval_status = Column(String, nullable=False, default="PENDING", index=True)
    status = Column(String, nullable=False, default="PREVIEWED", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class StrategyActivation(Base, TimestampMixin):
    __tablename__ = "strategy_activations"
    __table_args__ = (UniqueConstraint("intent_id", name="uq_strategy_activation_intent"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    intent_id = Column(String, ForeignKey("strategy_intents.id", ondelete="CASCADE"), nullable=False)
    execution_mode = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING", index=True)
    runtime_command_id = Column(String, nullable=True, index=True)
    runtime_ack_json = Column(JSON, default=dict, nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class StrategyRiskPolicy(Base, TimestampMixin):
    __tablename__ = "strategy_risk_policies"
    __table_args__ = (UniqueConstraint("strategy_id", "strategy_version", name="uq_strategy_risk_version"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    max_position = Column(Float, nullable=False)
    max_notional = Column(Float, nullable=False)
    max_leverage = Column(Float, nullable=False)
    max_daily_loss = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    max_orders_per_minute = Column(Integer, nullable=False)
    reduce_only = Column(Boolean, nullable=False, default=False)
    pause_opening = Column(Boolean, nullable=False, default=False)
    global_kill_switch = Column(Boolean, nullable=False, default=False)
    policy_json = Column(JSON, default=dict, nullable=False)


class StrategyRun(Base, TimestampMixin):
    __tablename__ = "strategy_runs"
    __table_args__ = (UniqueConstraint("runtime_run_id", name="uq_strategy_runtime_run"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    activation_id = Column(String, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True)
    runtime_run_id = Column(String, nullable=False)
    execution_mode = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING", index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    performance_json = Column(JSON, default=dict, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class SignalEvent(Base):
    __tablename__ = "signal_events"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_strategy_signal_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_ids = Column(JSON, default=list, nullable=False)
    source_urls = Column(JSON, default=list, nullable=False)
    data_timestamp = Column(DateTime(timezone=True), nullable=False)
    fetch_timestamp = Column(DateTime(timezone=True), nullable=False)
    freshness = Column(Float, nullable=False)
    credibility_score = Column(Float, nullable=False)
    sentiment_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    asset = Column(String, nullable=False, index=True)
    model_version = Column(String, nullable=False)
    feature_version = Column(String, nullable=False)
    signal_direction = Column(String, nullable=False)
    signal_strength = Column(Float, nullable=False)
    target_position = Column(Float, nullable=False)
    execution_note = Column(Text, nullable=True)
    risk_state = Column(String, nullable=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class OrderIntent(Base, TimestampMixin):
    __tablename__ = "order_intents"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_order_intent_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    strategy_version = Column(Integer, nullable=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    instrument = Column(String, nullable=False)
    venue = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    notional = Column(Float, nullable=False)
    leverage = Column(Float, nullable=False, default=1)
    order_type = Column(String, nullable=False)
    reduce_only = Column(Boolean, nullable=False, default=False)
    execution_mode = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PREVIEWED", index=True)
    risk_limits_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    confirmation_token_hash = Column(String, nullable=True)
    approval_status = Column(String, nullable=False, default="PENDING")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True)
    order_intent_id = Column(String, ForeignKey("order_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String, nullable=False, index=True)
    reasons = Column(JSON, default=list, nullable=False)
    limits_json = Column(JSON, default=dict, nullable=False)
    state_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class OrderJournal(Base):
    __tablename__ = "order_journal"
    __table_args__ = (
        UniqueConstraint("client_order_id", "sequence", name="uq_order_journal_sequence"),
        UniqueConstraint("idempotency_key", name="uq_order_journal_idempotency"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    order_intent_id = Column(String, ForeignKey("order_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    client_order_id = Column(String, nullable=False, index=True)
    exchange_order_id = Column(String, nullable=True, index=True)
    sequence = Column(Integer, nullable=False, default=1)
    state = Column(String, nullable=False, index=True)
    instrument = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    filled_quantity = Column(Float, nullable=False, default=0)
    remaining_quantity = Column(Float, nullable=False)
    average_price = Column(Float, nullable=True)
    reduce_only = Column(Boolean, nullable=False, default=False)
    event_json = Column(JSON, default=dict, nullable=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True)
    instrument = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    side = Column(String, nullable=False)
    average_price = Column(Float, nullable=False)
    mark_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False, default=0)
    realized_pnl = Column(Float, nullable=False, default=0)
    leverage = Column(Float, nullable=False, default=1)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    captured_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    available_margin = Column(Float, nullable=False)
    daily_pnl = Column(Float, nullable=False, default=0)
    drawdown = Column(Float, nullable=False, default=0)
    exposure = Column(Float, nullable=False, default=0)
    stale = Column(Boolean, nullable=False, default=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    captured_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class PortfolioAutopilotReview(Base, TimestampMixin):
    __tablename__ = "portfolio_autopilot_reviews"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    nav = Column(Float, nullable=False, default=0)
    account_count = Column(Integer, nullable=False, default=0)
    findings_json = Column(JSON, default=list, nullable=False)
    concentration_json = Column(JSON, default=dict, nullable=False)
    status = Column(String, nullable=False, default="COMPLETED", index=True)
    data_as_of = Column(DateTime(timezone=True), nullable=True)


class ReconciliationRecord(Base, TimestampMixin):
    __tablename__ = "reconciliation_records"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, nullable=False, default="PENDING", index=True)
    local_state_json = Column(JSON, default=dict, nullable=False)
    exchange_state_json = Column(JSON, default=dict, nullable=False)
    differences_json = Column(JSON, default=list, nullable=False)
    actions_json = Column(JSON, default=list, nullable=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class TradingAuditLog(Base):
    __tablename__ = "trading_audit_logs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_trading_audit_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String, ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    actor_type = Column(String, nullable=False, default="user")
    request_json = Column(JSON, default=dict, nullable=False)
    result_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
