from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, text
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
    membership_tier = Column(String, nullable=False, default="silver", index=True)
    # Explicit user consent for Agent memory personalization. Memory is never
    # injected into model context before this timestamp exists.
    memory_consent_granted_at = Column(DateTime(timezone=True), nullable=True)
    credit_balance = Column(Integer, nullable=False, default=150)
    stripe_customer_id = Column(String, nullable=True, index=True)
    google_user_id = Column(String, nullable=True, unique=True, index=True)
    avatar_url = Column(String, nullable=True)
    auth_provider = Column(String, nullable=False, default="mock")
    password_hash = Column(String, nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    email_verification_token = Column(String, nullable=True, unique=True, index=True)
    email_verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String, nullable=True, unique=True, index=True)
    password_reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
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
    credential_ciphertext = Column(JSON, nullable=True)

    user = relationship("User", back_populates="identities")


class MobileOAuthSession(Base):
    """Short-lived, single-use bridge between Google and a native PKCE client."""

    __tablename__ = "mobile_oauth_sessions"

    id = Column(String, primary_key=True, default=new_id)
    provider = Column(String, nullable=False, default="google", index=True)
    state = Column(String, nullable=False, unique=True, index=True)
    client_state = Column(String, nullable=False)
    client_nonce = Column(String, nullable=False)
    provider_nonce = Column(String, nullable=False)
    provider_code_verifier = Column(String, nullable=False)
    code_challenge = Column(String, nullable=False)
    redirect_uri = Column(String, nullable=False)
    exchange_code_hash = Column(String, nullable=True, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MobileWebSession(Base):
    __tablename__ = "mobile_web_sessions"

    id = Column(String, primary_key=True, default=new_id)
    code_hash = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    locale = Column(String, nullable=False, default="en")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class PushDevice(Base, TimestampMixin):
    __tablename__ = "push_devices"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    token_ciphertext = Column(JSON, nullable=False)
    platform = Column(String, nullable=False, default="ios")
    environment = Column(String, nullable=False, default="production", index=True)
    locale = Column(String, nullable=False, default="en")
    timezone = Column(String, nullable=False, default="UTC")
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


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
    channels = Column(JSON, nullable=True)  # multi-select: email|telegram|slack|imessage (web inbox always on)
    report_types = Column(JSON, nullable=True)  # subset of crypto_daily|us_daily|week_ahead_events|portfolio_daily; null = all
    failure_count = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)


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


def _prevent_credit_ledger_mutation(*_args, **_kwargs) -> None:
    raise RuntimeError("CreditLedger is append-only")


event.listen(CreditLedger, "before_update", _prevent_credit_ledger_mutation)
event.listen(CreditLedger, "before_delete", _prevent_credit_ledger_mutation)


class CreditReservationRecord(Base, TimestampMixin):
    __tablename__ = "credit_reservations"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    task_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="RESERVED", index=True)
    reserved_credits = Column(Integer, nullable=False)
    settled_credits = Column(Integer, nullable=True)
    quote_json = Column(JSON, default=dict, nullable=False)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    ledger_entry_id = Column(String, ForeignKey("credit_ledger.id"), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class CreditSettlementRecord(Base):
    __tablename__ = "credit_settlements"

    id = Column(String, primary_key=True, default=new_id)
    reservation_id = Column(
        String,
        ForeignKey("credit_reservations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    requested_actual_credits = Column(Integer, nullable=False)
    settled_credits = Column(Integer, nullable=False)
    adjustment = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="SETTLED")
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CreditRefundEvent(Base):
    __tablename__ = "credit_refund_events"

    id = Column(String, primary_key=True, default=new_id)
    reservation_id = Column(
        String,
        ForeignKey("credit_reservations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    credits = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CreditBudgetPolicy(Base, TimestampMixin):
    __tablename__ = "credit_budget_policies"
    __table_args__ = (
        UniqueConstraint("user_id", "automation_key", name="uq_credit_budget_user_automation"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    automation_key = Column(String, nullable=False, index=True)
    daily_limit = Column(Integer, nullable=False)
    monthly_limit = Column(Integer, nullable=False)
    per_run_limit = Column(Integer, nullable=False)
    alert_threshold_pct = Column(Integer, nullable=False, default=80)
    enabled = Column(Boolean, nullable=False, default=True)
    paused = Column(Boolean, nullable=False, default=False)
    pause_reason = Column(String, nullable=True)


class CreditRewardGrant(Base):
    __tablename__ = "credit_reward_grants"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reward_type = Column(String, nullable=False, index=True)
    credits = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    granted_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    ledger_entry_id = Column(String, ForeignKey("credit_ledger.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


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
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class GatewayProvider(Base, TimestampMixin):
    """A configured official upstream provider, never a user-supplied URL."""

    __tablename__ = "gateway_providers"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    health_status = Column(String, nullable=False, default="unknown", index=True)
    last_health_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)


class GatewayModel(Base, TimestampMixin):
    __tablename__ = "gateway_models"

    id = Column(String, primary_key=True, default=new_id)
    public_id = Column(String, nullable=False, unique=True, index=True)
    provider_id = Column(String, ForeignKey("gateway_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_model_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    capabilities_json = Column("capabilities", JSON, default=dict, nullable=False)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    routing_json = Column("routing", JSON, default=dict, nullable=False)
    active_pricing_id = Column(String, nullable=True, index=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)


class GatewayPricingPolicy(Base, TimestampMixin):
    __tablename__ = "gateway_pricing_policies"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False, unique=True, default="default")
    markup_bps = Column(Integer, nullable=False, default=3000)
    active = Column(Boolean, nullable=False, default=True, index=True)
    updated_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)


class GatewayPriceRevision(Base):
    """An immutable provider-pricing snapshot awaiting or receiving approval."""

    __tablename__ = "gateway_price_revisions"

    id = Column(String, primary_key=True, default=new_id)
    model_id = Column(String, ForeignKey("gateway_models.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    currency = Column(String, nullable=False, default="USD")
    markup_bps = Column(Integer, nullable=False, default=3000)
    official_prices_json = Column("official_prices", JSON, default=dict, nullable=False)
    final_prices_json = Column("final_prices", JSON, default=dict, nullable=False)
    source_type = Column(String, nullable=False, default="config")
    source_reference = Column(String, nullable=True)
    source_hash = Column(String, nullable=True, index=True)
    synced_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    notes = Column(String, nullable=True)


class GatewayAccount(Base, TimestampMixin):
    __tablename__ = "gateway_accounts"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    monthly_spend_limit_usd = Column(Numeric(18, 8), nullable=False, default=0)
    current_month_spend_usd = Column(Numeric(18, 8), nullable=False, default=0)
    current_month_started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class GatewayApiKey(Base, TimestampMixin):
    __tablename__ = "gateway_api_keys"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    key_hint = Column(String, nullable=False, index=True)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    last_four = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    rate_limit_rpm = Column(Integer, nullable=False, default=60)
    scopes_json = Column("scopes", JSON, default=lambda: ["chat"], nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    rotated_from_key_id = Column(String, ForeignKey("gateway_api_keys.id"), nullable=True)


class GatewayRequestLog(Base):
    __tablename__ = "gateway_request_logs"

    id = Column(String, primary_key=True, default=new_id)
    request_id = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    api_key_id = Column(String, ForeignKey("gateway_api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_id = Column(String, ForeignKey("gateway_providers.id", ondelete="SET NULL"), nullable=True, index=True)
    model_id = Column(String, ForeignKey("gateway_models.id", ondelete="SET NULL"), nullable=True, index=True)
    public_model = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    http_status = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_tokens = Column(Integer, nullable=False, default=0)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    long_context_tokens = Column(Integer, nullable=False, default=0)
    image_units = Column(Integer, nullable=False, default=0)
    audio_units = Column(Integer, nullable=False, default=0)
    search_units = Column(Integer, nullable=False, default=0)
    upload_units = Column(Integer, nullable=False, default=0)
    download_units = Column(Integer, nullable=False, default=0)
    batch_units = Column(Integer, nullable=False, default=0)
    provider_cost_usd = Column(Numeric(18, 8), nullable=False, default=0)
    retail_cost_usd = Column(Numeric(18, 8), nullable=False, default=0)
    ip_address = Column(String, nullable=True, index=True)
    error_code = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class GatewayProviderSync(Base):
    __tablename__ = "gateway_provider_syncs"

    id = Column(String, primary_key=True, default=new_id)
    provider_id = Column(String, ForeignKey("gateway_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending_review", index=True)
    triggered_by = Column(String, nullable=False, default="scheduler")
    triggered_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    models_seen = Column(Integer, nullable=False, default=0)
    prices_seen = Column(Integer, nullable=False, default=0)
    summary_json = Column("summary", JSON, default=dict, nullable=False)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class GatewayIPBlock(Base, TimestampMixin):
    __tablename__ = "gateway_ip_blocks"

    id = Column(String, primary_key=True, default=new_id)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    reason = Column(String, nullable=False)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


class GatewaySecurityEvent(Base):
    __tablename__ = "gateway_security_events"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    api_key_id = Column(String, ForeignKey("gateway_api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="warning", index=True)
    ip_address = Column(String, nullable=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


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
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    status = Column(String, nullable=False, default="completed", index=True)
    engine = Column(String, nullable=False, default="vectorbt")
    strategy_id = Column(String, nullable=True, index=True)
    strategy_version = Column(String, nullable=True)
    strategy_name = Column(String, nullable=False)
    asset = Column(String, nullable=False)
    params_json = Column(JSON, default=dict, nullable=False)
    result_json = Column(JSON, default=dict, nullable=False)
    spec_json = Column(JSON, default=dict, nullable=False)
    data_snapshot_json = Column(JSON, default=dict, nullable=False)
    assumptions_json = Column(JSON, default=dict, nullable=False)
    error_json = Column(JSON, default=dict, nullable=False)
    credits_spent = Column(Integer, nullable=False, default=0)
    credits_reserved = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BacktestArtifact(Base):
    """Durable result/export metadata; payloads live under the configured artifact root."""

    __tablename__ = "backtest_artifacts"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    backtest_id = Column(String, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_type = Column(String, nullable=False, index=True)
    format = Column(String, nullable=False, default="json")
    relative_path = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    checksum = Column(String, nullable=True)
    credits_spent = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BacktestCandle(Base):
    """Downloaded daily OHLCV bars shared by the backtest lab (BTC/ETH, 3y)."""

    __tablename__ = "backtest_candles"
    __table_args__ = (UniqueConstraint("symbol", "interval", "ts", name="uq_backtest_candle_symbol_interval_ts"),)

    id = Column(String, primary_key=True, default=new_id)
    symbol = Column(String, nullable=False, index=True)
    interval = Column(String, nullable=False, default="1d")
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    provider = Column(String, nullable=False, default="binance")
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BacktestLabRun(Base, TimestampMixin):
    """Nautilus-spec daily/cross-sectional strategy backtest produced by the lab."""

    __tablename__ = "backtest_lab_runs"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    status = Column(String, nullable=False, default="completed", index=True)
    mode = Column(String, nullable=False, default="daily")
    spec_json = Column(JSON, default=dict, nullable=False)
    symbols_json = Column(JSON, default=list, nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=True)
    window_end = Column(DateTime(timezone=True), nullable=True)
    performance_json = Column(JSON, default=dict, nullable=False)
    equity_json = Column(JSON, default=list, nullable=False)
    assumptions_json = Column(JSON, default=dict, nullable=False)
    context_used_json = Column(JSON, default=dict, nullable=False)
    error = Column(String, nullable=True)
    credits_spent = Column(Integer, nullable=False, default=0)


class ResearchRun(Base):
    """Isolated Python research run executed inside an ephemeral container."""

    __tablename__ = "research_runs"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    code_hash = Column(String, nullable=False, index=True)
    code = Column(Text, nullable=False)
    dataset_refs_json = Column(JSON, default=list, nullable=False)
    limits_json = Column(JSON, default=dict, nullable=False)
    metrics_json = Column(JSON, default=dict, nullable=False)
    figures_json = Column(JSON, default=list, nullable=False)
    logs = Column(Text, nullable=False, default="")
    error = Column(Text, nullable=True)
    credits_reserved = Column(Integer, nullable=False, default=0)
    credits_spent = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
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


class IMessageInboundEvent(Base, TimestampMixin):
    """Idempotency record for messages delivered by the macOS iMessage relay."""

    __tablename__ = "imessage_inbound_events"

    id = Column(String, primary_key=True, default=new_id)
    relay_message_id = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="processing", index=True)
    assistant_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)


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


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_skills_slug"),
        UniqueConstraint("scope", "owner_user_id", "workspace_id", "slug", name="uq_skill_scope_owner_slug"),
    )

    id = Column(String, primary_key=True, default=new_id)
    slug = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    publisher_name = Column(String, nullable=False)
    owner_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    scope = Column(String, nullable=False, default="personal", index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    current_version = Column(String, nullable=False, default="1.0.0")
    asset_classes_json = Column(JSON, default=list, nullable=False)
    risk_level = Column(String, nullable=False, default="low")
    billing_type = Column(String, nullable=False, default="included")
    allow_autopilot = Column(Boolean, nullable=False, default=False)
    allow_order_intent = Column(Boolean, nullable=False, default=False)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_version"),)

    id = Column(String, primary_key=True, default=new_id)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String, nullable=False)
    manifest_json = Column(JSON, default=dict, nullable=False)
    content_bundle_json = Column(JSON, default=dict, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    release_status = Column(String, nullable=False, default="draft", index=True)
    changelog = Column(Text, nullable=False, default="")
    validation_json = Column(JSON, default=dict, nullable=False)
    created_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SkillInstallation(Base, TimestampMixin):
    __tablename__ = "skill_installations"
    __table_args__ = (
        UniqueConstraint("skill_id", "target_key", name="uq_skill_installation_target"),
    )

    id = Column(String, primary_key=True, default=new_id)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    installed_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_key = Column(String, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    pinned_version = Column(String, nullable=True)
    config_overrides_json = Column(JSON, default=dict, nullable=False)


class SkillRun(Base):
    __tablename__ = "skill_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_skill_run_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_version_id = Column(String, ForeignKey("skill_versions.id", ondelete="RESTRICT"), nullable=False, index=True)
    installation_id = Column(String, ForeignKey("skill_installations.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    agent_run_id = Column(String, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    external_run_id = Column(String, nullable=True, index=True)
    trigger_source = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="reserved", index=True)
    input_summary_json = Column(JSON, default=dict, nullable=False)
    output_summary = Column(Text, nullable=True)
    evidence_json = Column(JSON, default=dict, nullable=False)
    usage_json = Column(JSON, default=dict, nullable=False)
    credits_reserved = Column(Integer, nullable=False, default=0)
    credits_used = Column(Integer, nullable=False, default=0)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    trace_id = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class SkillPermission(Base):
    __tablename__ = "skill_permissions"
    __table_args__ = (
        UniqueConstraint("skill_version_id", "permission_type", "resource", "effect", name="uq_skill_version_permission"),
    )

    id = Column(String, primary_key=True, default=new_id)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_version_id = Column(String, ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_type = Column(String, nullable=False, index=True)
    resource = Column(String, nullable=False)
    effect = Column(String, nullable=False, default="allow")
    constraints_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SkillSource(Base):
    __tablename__ = "skill_sources"

    id = Column(String, primary_key=True, default=new_id)
    skill_id = Column(String, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_version_id = Column(String, ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    repo_url = Column(Text, nullable=True)
    commit_hash = Column(String, nullable=True, index=True)
    trust_status = Column(String, nullable=False, default="untrusted", index=True)
    imported_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    imported_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


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


class PortfolioInvestmentTransaction(Base, TimestampMixin):
    """Normalized read-only investment activity received from Plaid.

    The encrypted Plaid Item access token is deliberately kept on
    ``ExchangeConnection`` only. This table contains the minimum user-authorized
    transaction fields required for portfolio history and never exposes it.
    """

    __tablename__ = "portfolio_investment_transactions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "provider",
            "external_id",
            name="uq_portfolio_investment_transaction_external",
        ),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, default="plaid", index=True)
    external_id = Column(String, nullable=False)
    provider_account_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=True, index=True)
    posted_date = Column(Date, nullable=False, index=True)
    transaction_datetime = Column(DateTime(timezone=True), nullable=True)
    name = Column(String, nullable=False)
    symbol = Column(String, nullable=True, index=True)
    transaction_type = Column(String, nullable=False)
    subtype = Column(String, nullable=True)
    quantity = Column(Float, nullable=False, default=0)
    price = Column(Float, nullable=False, default=0)
    amount = Column(Float, nullable=False, default=0)
    fees = Column(Float, nullable=False, default=0)
    currency = Column(String, nullable=True)
    cancelled = Column(Boolean, nullable=False, default=False)
    raw_event_reference = Column(JSON, default=dict, nullable=False)


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


class PortfolioNavSnapshot(Base, TimestampMixin):
    """Daily per-user portfolio NAV snapshot (estimated, not an official statement).

    ``total_nav`` is the sum of the latest account equity across every connected
    portfolio account; ``positions_json`` holds the per-symbol detail
    (quantity, mark price, market value, unrealized PnL). The ``partial`` flag
    records whether any account source failed during the run so consumers can
    label the figure as estimated/partial. A ``(user_id, snapshot_date)`` row is
    idempotent: the daily job upserts it.
    """

    __tablename__ = "portfolio_nav_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_portfolio_nav_user_date"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    total_nav = Column(Float, nullable=False, default=0)
    cash_balance = Column(Float, nullable=False, default=0)
    account_count = Column(Integer, nullable=False, default=0)
    positions_json = Column(JSON, default=dict, nullable=False)
    source_accounts_json = Column(JSON, default=list, nullable=False)
    partial = Column(Boolean, nullable=False, default=False)
    data_as_of = Column(DateTime(timezone=True), nullable=True)
    captured_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


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
    trace_id = Column(String, nullable=True, index=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class ResearchSnapshot(Base):
    """One shared research build per cycle: market facts are produced once and
    then personalized per user. kind: overnight | crypto_daily | us_daily | intraday."""

    __tablename__ = "research_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    kind = Column(String, nullable=False, index=True)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)
    data_cutoff_at = Column(DateTime(timezone=True), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=True)
    window_end = Column(DateTime(timezone=True), nullable=True)
    summary_markdown = Column(Text, nullable=False, default="")
    source_counts_json = Column(JSON, default=dict, nullable=False)
    health_json = Column(JSON, default=dict, nullable=False)
    status = Column(String, nullable=False, default="completed", index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MarketEvent(Base):
    """A deduplicated, evidence-backed market event.

    Every event records source provenance, collection and data-cutoff times,
    a dedup fingerprint, related assets, possible direction/horizon, confidence,
    supporting evidence and evidence gaps. Facts never come from an LLM; an LLM
    may only interpret already-stored evidence.
    """

    __tablename__ = "market_events"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_market_event_fingerprint"),)

    id = Column(String, primary_key=True, default=new_id)
    event_type = Column(String, nullable=False, index=True)  # price_move | news | earnings_confirmed | macro_scheduled | options_regime | funding_oi
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False, default="")
    source_provider = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=True)
    source_published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    collected_at = Column(DateTime(timezone=True), nullable=False)
    data_cutoff_at = Column(DateTime(timezone=True), nullable=False)
    fingerprint = Column(String, nullable=False)
    assets = Column(JSON, default=list, nullable=False)
    direction = Column(String, nullable=True)  # up | down | mixed | unknown
    time_horizon = Column(String, nullable=True)  # intraday | days | weeks
    confidence = Column(Float, nullable=False, default=0.0)
    evidence_json = Column(JSON, default=list, nullable=False)
    evidence_gaps = Column(JSON, default=list, nullable=False)
    research_snapshot_id = Column(String, ForeignKey("research_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AssetImpact(Base):
    """Event -> asset impact. relation_type distinguishes direct causation from
    industry/macro/counterparty linkage and pure statistical correlation."""

    __tablename__ = "asset_impacts"
    __table_args__ = (UniqueConstraint("event_id", "symbol", "relation_type", name="uq_asset_impact_event_symbol_relation"),)

    id = Column(String, primary_key=True, default=new_id)
    event_id = Column(String, ForeignKey("market_events.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    relation_type = Column(String, nullable=False, default="direct")  # direct | industry | macro | counterparty | statistical
    direction = Column(String, nullable=True)
    magnitude = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    horizon = Column(String, nullable=True)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserPortfolioImpact(Base):
    """Per-user mapping of an asset impact onto actual holdings."""

    __tablename__ = "user_portfolio_impacts"
    __table_args__ = (UniqueConstraint("user_id", "event_id", "symbol", name="uq_user_portfolio_impact"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String, ForeignKey("market_events.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_impact_id = Column(String, ForeignKey("asset_impacts.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String, nullable=False)
    exposure_value = Column(Float, nullable=False, default=0.0)
    exposure_weight = Column(Float, nullable=True)
    direction = Column(String, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    computed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ResearchAction(Base):
    """A recommended next step derived from events/impacts."""

    __tablename__ = "research_actions"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_research_action_dedup"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    event_id = Column(String, ForeignKey("market_events.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = Column(String, nullable=False, index=True)  # ask_agent | add_alert | add_to_report | generate_report | create_strategy | run_backtest
    title = Column(String, nullable=False)
    payload_json = Column(JSON, default=dict, nullable=False)
    status = Column(String, nullable=False, default="open", index=True)
    dedup_key = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class CustodyAccount(Base, TimestampMixin):
    """A real custody venue account (testnet/sandbox first). Distinct from
    TradingAccount: this is the funds-custody domain, not a trading handle."""

    __tablename__ = "custody_accounts"

    id = Column(String, primary_key=True, default=new_id)
    venue = Column(String, nullable=False, index=True)
    environment = Column(String, nullable=False, default="testnet")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    deposit_address = Column(String, nullable=True)
    provider_ref = Column(String, nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)


class CustodySubAccount(Base, TimestampMixin):
    """Per-user, per-asset sub-ledger with available/frozen balances."""

    __tablename__ = "custody_sub_accounts"
    __table_args__ = (UniqueConstraint("custody_account_id", "user_id", "asset", name="uq_custody_sub_account"),)

    id = Column(String, primary_key=True, default=new_id)
    custody_account_id = Column(String, ForeignKey("custody_accounts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset = Column(String, nullable=False)
    available = Column(Numeric(38, 18), nullable=False, default=0)
    frozen = Column(Numeric(38, 18), nullable=False, default=0)


class CustodyLedgerEntry(Base):
    """Append-only custody ledger; every balance mutation is an entry."""

    __tablename__ = "custody_ledger_entries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_custody_ledger_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    sub_account_id = Column(String, ForeignKey("custody_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String, nullable=False, index=True)  # deposit_confirm | freeze | unfreeze | trade_debit | trade_credit | withdrawal_hold | withdrawal_release | reconcile_adjust
    amount = Column(Numeric(38, 18), nullable=False)
    available_after = Column(Numeric(38, 18), nullable=False)
    frozen_after = Column(Numeric(38, 18), nullable=False)
    ref_type = Column(String, nullable=True)
    ref_id = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CustodyDeposit(Base):
    __tablename__ = "custody_deposits"
    __table_args__ = (UniqueConstraint("external_ref", name="uq_custody_deposit_external_ref"),)

    id = Column(String, primary_key=True, default=new_id)
    sub_account_id = Column(String, ForeignKey("custody_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    asset = Column(String, nullable=False)
    amount = Column(Numeric(38, 18), nullable=False)
    tx_ref = Column(String, nullable=False)
    confirmations = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | confirmed | credited
    external_ref = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class CustodyWithdrawal(Base, TimestampMixin):
    __tablename__ = "custody_withdrawals"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_custody_withdrawal_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    sub_account_id = Column(String, ForeignKey("custody_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    asset = Column(String, nullable=False)
    amount = Column(Numeric(38, 18), nullable=False)
    address = Column(String, nullable=False)
    status = Column(String, nullable=False, default="intent", index=True)  # intent | approved | submitted | confirmed | failed | rejected
    idempotency_key = Column(String, nullable=False)
    tx_ref = Column(String, nullable=True)
    error = Column(String, nullable=True)


class CustodyReconciliation(Base):
    __tablename__ = "custody_reconciliations"

    id = Column(String, primary_key=True, default=new_id)
    custody_account_id = Column(String, ForeignKey("custody_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    asset = Column(String, nullable=False)
    local_available = Column(Numeric(38, 18), nullable=False)
    local_frozen = Column(Numeric(38, 18), nullable=False)
    external_balance = Column(Numeric(38, 18), nullable=True)
    difference = Column(Numeric(38, 18), nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    details_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class GatewayWallet(Base, TimestampMixin):
    """Prepaid USD balance dedicated to API Gateway usage.

    This is intentionally separate from ``User.credit_balance``. The latter
    pays for the PureGamma product; it must never be changed by Gateway
    purchases or metered API requests.
    """

    __tablename__ = "gateway_wallets"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    available_balance_usd = Column(Numeric(18, 8), nullable=False, default=0)
    lifetime_credited_usd = Column(Numeric(18, 8), nullable=False, default=0)
    lifetime_debited_usd = Column(Numeric(18, 8), nullable=False, default=0)


class GatewayTopupIntent(Base):
    """One user-selected Stripe Checkout payment for a Gateway wallet."""

    __tablename__ = "gateway_topup_intents"

    id = Column(String, primary_key=True, default=new_id)
    public_reference = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(String, nullable=False, default="created", index=True)
    stripe_checkout_session_id = Column(String, nullable=True, unique=True, index=True)
    stripe_payment_intent_id = Column(String, nullable=True, unique=True, index=True)
    stripe_customer_id = Column(String, nullable=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class GatewayWalletLedger(Base):
    """Immutable Gateway wallet credits and usage debits."""

    __tablename__ = "gateway_wallet_ledger"

    id = Column(String, primary_key=True, default=new_id)
    wallet_id = Column(String, ForeignKey("gateway_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String, nullable=False, index=True)
    amount_usd = Column(Numeric(18, 8), nullable=False)
    balance_after_usd = Column(Numeric(18, 8), nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    topup_intent_id = Column(String, ForeignKey("gateway_topup_intents.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    gateway_request_log_id = Column(String, ForeignKey("gateway_request_logs.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


# =============================================================================
# DeepSeek Harness Integration (additive layer; see
# docs/developer/HARNESS_RESEARCH_ARCHITECTURE.md). The Harness runner is a
# research orchestrator only: it can never create orders, touch accounts, or
# read production secrets. Trading remains exclusively on the
# Trading Control Plane -> Nautilus Runtime path.
# =============================================================================


class EvidenceSnapshot(Base, TimestampMixin):
    """Immutable, hashable facts frozen at the start of one research run.

    Rows are INSERT-only: SQLAlchemy events reject update/delete. Shared
    market evidence may have ``user_id`` NULL; user-scoped evidence always
    carries the owning user. Uniqueness is enforced with two PARTIAL unique
    indexes so NULL-owner shared snapshots are still deduplicated:
    (content_hash, source_scope) WHERE user_id IS NULL, and
    (content_hash, source_scope, user_id) WHERE user_id IS NOT NULL.
    """

    __tablename__ = "evidence_snapshots"
    __table_args__ = (
        Index(
            "uq_evidence_snapshot_shared_scope",
            "content_hash",
            "source_scope",
            unique=True,
            sqlite_where=text("user_id IS NULL"),
            postgresql_where=text("user_id IS NULL"),
        ),
        Index(
            "uq_evidence_snapshot_user_scope",
            "content_hash",
            "source_scope",
            "user_id",
            unique=True,
            sqlite_where=text("user_id IS NOT NULL"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    schema_version = Column(String, nullable=False, default="1.0")
    source_scope = Column(String, nullable=False, default="run", index=True)  # run | shared_market | portfolio
    freshness_window_seconds = Column(Integer, nullable=False, default=900)
    content_hash = Column(String, nullable=False, index=True)
    normalized_evidence_json = Column(JSON, default=dict, nullable=False)
    source_ids_json = Column(JSON, default=list, nullable=False)
    provider_list_json = Column(JSON, default=list, nullable=False)
    source_timestamps_json = Column(JSON, default=list, nullable=False)
    fetched_timestamps_json = Column(JSON, default=list, nullable=False)
    mock_fallback_flags_json = Column(JSON, default=list, nullable=False)
    authorization_context_json = Column(JSON, default=dict, nullable=False)


class HarnessResearchRun(Base, TimestampMixin):
    """One deep-research execution delegated to the isolated Harness runner.

    State machine: queued -> preparing -> running -> validating ->
    completed | degraded | failed | canceled | timed_out. Every transition is
    recorded in ``harness_run_state_transitions`` and is idempotent.
    """

    __tablename__ = "harness_research_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_harness_run_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_agent_run_id = Column(String, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    skill_run_id = Column(String, ForeignKey("skill_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    requested_goal_summary = Column(Text, nullable=False, default="")
    input_hash = Column(String, nullable=False, index=True)
    evidence_snapshot_id = Column(String, ForeignKey("evidence_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_snapshot_hash = Column(String, nullable=True)
    harness_version = Column(String, nullable=False)
    runtime_version = Column(String, nullable=False)
    cordis_config_hash = Column(String, nullable=False)
    plugin_lock_hash = Column(String, nullable=False)
    provider = Column(String, nullable=False, default="deepseek")
    model = Column(String, nullable=False, default="deepseek-v4-flash")
    session_id = Column(String, nullable=True, index=True)
    queue_task_id = Column(String, nullable=True, index=True)
    queue_priority = Column(Integer, nullable=False, default=0)
    max_budget_credits = Column(Integer, nullable=False, default=0)
    credits_reserved = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    timeout_at = Column(DateTime(timezone=True), nullable=True, index=True)
    error_code = Column(String, nullable=True)
    error_summary = Column(Text, nullable=True)
    usage_json = Column(JSON, default=dict, nullable=False)
    artifact_id = Column(String, nullable=True, index=True)  # research_artifacts.id (plain ref: avoids a circular FK)
    idempotency_key = Column(String, nullable=False)
    trace_id = Column(String, nullable=False, index=True)
    settlement_status = Column(String, nullable=True, default="none", index=True)  # none | settled | refunded


class HarnessRunStateTransition(Base):
    """Append-only audit of every HarnessResearchRun status change."""

    __tablename__ = "harness_run_state_transitions"

    id = Column(String, primary_key=True, default=new_id)
    research_run_id = Column(String, ForeignKey("harness_research_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String, nullable=False)
    to_status = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=True)
    actor = Column(String, nullable=False, default="system")  # system | user | orchestrator | gateway
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class ResearchArtifact(Base):
    """Server-validated structured output of a Harness research run.

    Harness can only *propose* an artifact through the Research Gateway;
    the control plane validates citations/evidence before persisting.
    """

    __tablename__ = "research_artifacts"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    research_run_id = Column(String, ForeignKey("harness_research_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)  # draft | validated | degraded | rejected
    schema_version = Column(String, nullable=False, default="1.0")
    structured_json = Column(JSON, default=dict, nullable=False)
    markdown_rendering = Column(Text, nullable=False, default="")
    citations_json = Column(JSON, default=list, nullable=False)
    methodology = Column(Text, nullable=False, default="")
    assumptions_json = Column(JSON, default=list, nullable=False)
    limitations_json = Column(JSON, default=list, nullable=False)
    tool_run_summaries_json = Column(JSON, default=list, nullable=False)
    artifact_file_refs_json = Column(JSON, default=list, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    validation_result_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class StrategyRelease(Base):
    """Immutable, human-reviewed strategy release.

    TradingMandate can only reference an approved StrategyRelease; it must
    never reference Harness-generated natural language or drafts.
    """

    __tablename__ = "strategy_releases"
    __table_args__ = (
        UniqueConstraint("strategy_id", "strategy_version", "release_number", name="uq_strategy_release_version"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_version = Column(Integer, nullable=False)
    release_number = Column(Integer, nullable=False, default=1)
    spec_json = Column(JSON, default=dict, nullable=False)
    spec_hash = Column(String, nullable=False, index=True)
    review_status = Column(String, nullable=False, default="pending", index=True)  # pending | approved | rejected
    reviewed_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=False, default="user")  # user | harness_proposal | admin
    source_artifact_id = Column(String, ForeignKey("research_artifacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class TradingMandate(Base, TimestampMixin):
    """User-authorized trading authorization envelope.

    PAPER and SHADOW mandates use the existing strategy control path.
    LIVE mandates are read-only for everyone except the Trading Control
    Plane: orders can only flow through RiskCheck -> OrderIntent ->
    Execution Gateway -> Ledger -> NAV Snapshot. Auto-pause is automatic;
    resume always requires explicit human confirmation.
    """

    __tablename__ = "trading_mandates"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_trading_mandate_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_release_id = Column(String, ForeignKey("strategy_releases.id", ondelete="RESTRICT"), nullable=False, index=True)
    broker_connection_id = Column(String, ForeignKey("broker_connections.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_mode = Column(String, nullable=False, default="shadow", index=True)  # shadow | paper | live
    environment = Column(String, nullable=False, default="paper", index=True)  # paper | testnet | production
    # Lifecycle status of the mandate itself (independent from approval and pause):
    # draft | active | paused | suspended | revoked | expired
    status = Column(String, nullable=False, default="draft", index=True)
    allowed_symbols_json = Column(JSON, default=list, nullable=False)
    allowed_side = Column(String, nullable=False, default="both")  # long | short | both
    # Financial risk thresholds must never use binary floating point.
    max_total_notional = Column(Numeric(20, 8), nullable=False, default=0)
    max_per_order_notional = Column(Numeric(20, 8), nullable=False, default=0)
    max_position_notional = Column(Numeric(20, 8), nullable=False, default=0)
    max_leverage = Column(Numeric(20, 8), nullable=False, default=1)
    max_daily_loss = Column(Numeric(20, 8), nullable=False, default=0)
    max_trades_per_day = Column(Integer, nullable=False, default=0)
    max_order_frequency_seconds = Column(Integer, nullable=False, default=60)
    allowed_time_windows_json = Column(JSON, default=list, nullable=False)
    data_freshness_seconds = Column(Integer, nullable=False, default=300)
    source_policy_json = Column(JSON, default=dict, nullable=False)
    stop_conditions_json = Column(JSON, default=list, nullable=False)
    kill_switch_state = Column(String, nullable=False, default="inactive", index=True)  # inactive | active
    paused = Column(Boolean, nullable=False, default=False)
    pause_reason = Column(Text, nullable=True)
    approval_status = Column(String, nullable=False, default="pending", index=True)  # pending | approved | rejected | revoked | expired
    approved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmation_phrase_hash = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    audit_metadata_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)


class TradingMandateAudit(Base):
    """Append-only audit for every mandate lifecycle and execution event."""

    __tablename__ = "trading_mandate_audits"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_mandate_audit_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)  # created | approved | rejected | revoked | paused | resumed | killed | execution | rejection
    status = Column(String, nullable=False, index=True)
    actor_type = Column(String, nullable=False, default="user")  # user | system | harness_suggestion | scheduler
    strategy_version = Column(Integer, nullable=True)
    signal_id = Column(String, nullable=True, index=True)
    runtime_command_id = Column(String, nullable=True)
    detail_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


# =============================================================================
# LIVE Trading Control Plane (additive layer). Everything below is gated by the
# LIVE feature flag AND user approval AND mandate approval AND kill switches.
# Real secrets never reach these tables in plaintext: BrokerConnection stores
# only a KMS reference or Fernet ciphertext (see packages/live_trading).
# =============================================================================


class BrokerConnection(Base, TimestampMixin):
    """One broker/exchange connection owned by a user.

    ``encrypted_credentials_ref`` holds either a Secret-Manager/KMS reference
    (``kms://...``) or Fernet ciphertext produced by
    ``packages.live_trading.secret_store``. Plaintext credentials must never be
    persisted here or anywhere else in the database.
    """

    __tablename__ = "broker_connections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "account_label", name="uq_broker_connection_label"
        ),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)  # e.g. binance_spot | coinbase_advanced
    account_label = Column(String, nullable=False)
    encrypted_credentials_ref = Column(Text, nullable=True)
    permissions_json = Column(
        JSON,
        default=lambda: {
            "spot": True,
            "margin": False,
            "futures": False,
            "options": False,
            "shorting": False,
            "withdraw": False,
            "transfer": False,
        },
        nullable=False,
    )
    environment = Column(String, nullable=False, default="paper", index=True)  # paper | testnet | production
    status = Column(String, nullable=False, default="DISCONNECTED", index=True)  # DISCONNECTED | CONNECTED | HEALTHY | ERROR | REVOKED
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class LiveUserApproval(Base, TimestampMixin):
    """Server-side LIVE eligibility approval for a user.

    No user, admin web UI, or mobile client can self-approve: this row can
    only be created/updated by the admin kill-switch/approval endpoints.
    """

    __tablename__ = "live_user_approvals"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | approved | rejected | revoked
    max_total_notional = Column(Numeric(20, 8), nullable=False, default=0)
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)


class TradingKillSwitch(Base, TimestampMixin):
    """Append-only kill switch states (global | user | mandate | connection).

    Engaging a switch is immediate and irreversible except through an explicit
    admin release (``resolved_by`` is required). The trading control plane
    checks every scope before allowing any new order.
    """

    __tablename__ = "trading_kill_switches"

    id = Column(String, primary_key=True, default=new_id)
    scope = Column(String, nullable=False, index=True)  # global | user | mandate | connection
    scope_id = Column(String, nullable=True, index=True)
    state = Column(String, nullable=False, default="active", index=True)  # active | inactive
    reason = Column(Text, nullable=False, default="")
    triggered_by = Column(String, nullable=False, default="admin", index=True)  # admin | risk_engine | reconciliation | system
    triggered_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    trace_id = Column(String, nullable=True, index=True)


class MarketPriceSnapshot(Base):
    """Latest valid market price per symbol/venue for NAV marking.

    Prices are recorded by the server price feed only; client timestamps are
    never trusted. Staleness is evaluated at read time against
    ``LIVE_NAV_PRICE_STALE_SECONDS``.
    """

    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        Index("ix_market_price_lookup", "symbol", "venue", "captured_at"),
    )

    id = Column(String, primary_key=True, default=new_id)
    symbol = Column(String, nullable=False, index=True)
    venue = Column(String, nullable=False, default="MOCK")
    price = Column(Numeric(20, 8), nullable=False)
    captured_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    source = Column(String, nullable=False, default="runtime")  # runtime | gateway | manual
    trace_id = Column(String, nullable=True)


class LiveOrderIntent(Base, TimestampMixin):
    """A validated, risk-checked intent for a LIVE order.

    ``source`` is strictly controlled: the Harness can only produce
    ``strategy`` suggestions; a real LIVE submission always flows through user
    confirmation (``user_confirmed``), an admin (``admin``) or the system
    (``system``). ``live_order`` is reserved and never accepted.
    """

    __tablename__ = "live_order_intents"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_live_order_intent_idempotency"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_release_id = Column(String, ForeignKey("strategy_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    broker_connection_id = Column(String, ForeignKey("broker_connections.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False, index=True)  # buy | sell
    quantity = Column(Numeric(20, 8), nullable=False)
    order_type = Column(String, nullable=False, default="market")  # market | limit
    limit_price = Column(Numeric(20, 8), nullable=True)
    client_order_id = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False)
    source = Column(String, nullable=False, default="user_confirmed", index=True)  # user_confirmed | strategy | admin | system
    requested_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String, nullable=False, default="PENDING", index=True)  # PENDING | APPROVED | REJECTED | EXPIRED | CANCELED
    confirmation_token_hash = Column(String, nullable=True)
    trace_id = Column(String, nullable=False, index=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class RiskCheck(Base):
    """Immutable risk engine verdict for one order intent.

    INSERT-only: SQLAlchemy events reject update/delete, so a check can never
    be rewritten after the fact.
    """

    __tablename__ = "risk_checks"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_intent_id = Column(String, ForeignKey("live_order_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="CASCADE"), nullable=False, index=True)
    result = Column(String, nullable=False, index=True)  # PASS | REJECT
    rejection_reason = Column(Text, nullable=True)
    checks_json = Column(JSON, default=list, nullable=False)
    checked_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    risk_engine_version = Column(String, nullable=False, index=True)
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class LiveOrder(Base, TimestampMixin):
    """Server-submitted LIVE order state (submitted to the broker via the
    Execution Gateway). Never client-submitted directly."""

    __tablename__ = "live_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_live_order_idempotency"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="CASCADE"), nullable=False, index=True)
    order_intent_id = Column(String, ForeignKey("live_order_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_connection_id = Column(String, ForeignKey("broker_connections.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False, index=True)  # buy | sell
    quantity = Column(Numeric(20, 8), nullable=False)
    order_type = Column(String, nullable=False, default="market")
    limit_price = Column(Numeric(20, 8), nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | submitted | accepted | partially_filled | filled | canceled | rejected | expired | unknown
    client_order_id = Column(String, nullable=False, index=True)
    broker_order_id = Column(String, nullable=True, index=True)
    filled_quantity = Column(Numeric(20, 8), nullable=False, default=0)
    average_price = Column(Numeric(20, 8), nullable=True)
    idempotency_key = Column(String, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    trace_id = Column(String, nullable=False, index=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    raw_ack_json = Column(JSON, default=dict, nullable=False)


class Fill(Base):
    """An actual broker fill. INSERT-only (immutable)."""

    __tablename__ = "fills"
    __table_args__ = (UniqueConstraint("broker_fill_id", name="uq_fill_broker_fill_id"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(String, ForeignKey("live_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="SET NULL"), nullable=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False, index=True)  # buy | sell
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=False)
    fee = Column(Numeric(20, 8), nullable=False, default=0)
    fee_currency = Column(String, nullable=False, default="USD")
    executed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    broker_fill_id = Column(String, nullable=False)
    raw_reference_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class LedgerEntry(Base):
    """Immutable append-only ledger. UPDATE/DELETE are rejected by SQLAlchemy
    events; reconciliation differences are recorded as new
    ``reconciliation_adjustment`` entries and NEVER rewrite history."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ledger_entry_idempotency"),
        Index("ix_ledger_entries_account_created", "account_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="SET NULL"), nullable=True, index=True)
    entry_type = Column(String, nullable=False, index=True)  # cash_deposit | cash_withdrawal | trade_buy | trade_sell | fee | funding | dividend | adjustment | reconciliation_adjustment
    ref_type = Column(String, nullable=True)  # fill | order | deposit | withdrawal | manual | reconciliation
    ref_id = Column(String, nullable=True, index=True)
    symbol = Column(String, nullable=True)
    quantity = Column(Numeric(20, 8), nullable=True)
    price = Column(Numeric(20, 8), nullable=True)
    amount = Column(Numeric(20, 8), nullable=False)  # signed cash effect in account currency
    currency = Column(String, nullable=False, default="USD")
    balance_after = Column(Numeric(20, 8), nullable=True)
    idempotency_key = Column(String, nullable=False)
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class NavSnapshot(Base):
    """Server-computed NAV snapshot per account.

    ``nav`` is NULL when no valid price exists for a non-zero position — the
    server never fabricates valuations. Consumers must surface the snapshot as
    stale/unknown in that case.
    """

    __tablename__ = "nav_snapshots"
    __table_args__ = (
        Index("ix_nav_snapshots_account_calculated", "account_id", "calculated_at"),
    )

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="SET NULL"), nullable=True, index=True)
    nav = Column(Numeric(20, 8), nullable=True)  # NULL = stale/unpriced, never fabricated
    cash = Column(Numeric(20, 8), nullable=False, default=0)
    gross_exposure = Column(Numeric(20, 8), nullable=False, default=0)
    net_exposure = Column(Numeric(20, 8), nullable=False, default=0)
    realized_pnl = Column(Numeric(20, 8), nullable=False, default=0)
    unrealized_pnl = Column(Numeric(20, 8), nullable=False, default=0)
    currency = Column(String, nullable=False, default="USD")
    price_timestamp = Column(DateTime(timezone=True), nullable=True)
    calculated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    is_stale = Column(Boolean, nullable=False, default=False, index=True)
    calculation_version = Column(String, nullable=False, default="1.0.0")
    reconciliation_status = Column(String, nullable=False, default="pending", index=True)  # pending | ok | discrepancy


class TradingReconciliation(Base):
    """Daily exchange vs ledger vs NAV comparison. Append-only record of
    differences and the actions taken (mandate pause etc.)."""

    __tablename__ = "trading_reconciliations"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id = Column(String, ForeignKey("trading_mandates.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="ok", index=True)  # ok | discrepancy | error
    exchange_balance_json = Column(JSON, default=dict, nullable=False)
    ledger_balance_json = Column(JSON, default=dict, nullable=False)
    nav_json = Column(JSON, default=dict, nullable=False)
    differences_json = Column(JSON, default=list, nullable=False)
    actions_json = Column(JSON, default=list, nullable=False)
    resolved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class HarnessEventOutbox(Base):
    """DB outbox for harness/mandate domain events (future Redis Streams).

    Consumers use the idempotency key; retries must never duplicate
    notifications. Existing daily-report/email automation is untouched.
    """

    __tablename__ = "harness_event_outbox"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_harness_outbox_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    payload_json = Column(JSON, default=dict, nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | dispatched | failed
    trace_id = Column(String, nullable=False, index=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)


# =============================================================================
# Memory Service (PureGamma-owned). Models and Harness NEVER write user memory
# directly: everything flows through MemoryProposal -> Memory Policy -> user
# confirmation or low-risk auto-accept -> immutable audit -> structured write.
# Memory can never authorize, alter, or influence trading decisions, risk
# limits, or order permissions.
# =============================================================================


class ConversationMemorySummary(Base, TimestampMixin):
    """Short-term per-conversation memory: bounded window + compacted summary.

    Scoped to one conversation_id. Deleted with the conversation
    (ondelete=CASCADE). Never stores secrets, payment data, private keys, or
    unverified market conclusions.
    """

    __tablename__ = "conversation_memory_summaries"
    __table_args__ = (UniqueConstraint("conversation_id", "version", name="uq_conversation_memory_version"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    summary_text = Column(Text, nullable=False, default="")
    summary_token_estimate = Column(Integer, nullable=False, default=0)
    recent_message_ids_json = Column(JSON, default=list, nullable=False)
    source_message_ids_json = Column(JSON, default=list, nullable=False)
    goals_json = Column(JSON, default=list, nullable=False)
    known_facts_json = Column(JSON, default=list, nullable=False)
    used_evidence_json = Column(JSON, default=list, nullable=False)
    open_questions_json = Column(JSON, default=list, nullable=False)
    user_preferences_json = Column(JSON, default=list, nullable=False)
    superseded_by = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


class UserMemory(Base):
    """Medium-term structured user memory, owned by PureGamma.

    Namespaces are strongly isolated (chat/secretary/research/portfolio/
    trading). The trading namespace rejects writes by policy.
    """

    __tablename__ = "user_memories"
    __table_args__ = (UniqueConstraint("user_id", "namespace", "source_hash", name="uq_user_memory_source"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    namespace = Column(String, nullable=False, index=True)  # chat | secretary | research | portfolio | trading
    kind = Column(String, nullable=False, index=True)
    content_json = Column(JSON, default=dict, nullable=False)
    source_type = Column(String, nullable=False)  # model_proposal | deterministic | user_confirmed
    source_id = Column(String, nullable=True, index=True)
    source_hash = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=0.5)
    salience = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="active", index=True)  # active | archived | expired | superseded
    created_by = Column(String, nullable=False, default="model_proposed")  # user_confirmed | deterministic | model_proposed
    consent_scope = Column(String, nullable=False, default="none")  # chat | secretary | research | none
    tags_json = Column(JSON, default=list, nullable=False)
    superseded_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


class MemoryScopeSetting(Base, TimestampMixin):
    """Per-user opt-out/opt-in switches for each memory scope."""

    __tablename__ = "memory_scope_settings"
    __table_args__ = (UniqueConstraint("user_id", "scope", name="uq_memory_scope_user_scope"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope = Column(String, nullable=False, index=True)  # chat | secretary | research | portfolio | trading
    enabled = Column(Boolean, nullable=False, default=True)
    changed_by = Column(String, nullable=False, default="user")


class MemoryProposal(Base, TimestampMixin):
    """A proposed memory entry awaiting policy decision and consent."""

    __tablename__ = "memory_proposals"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_memory_proposal_idempotency"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    proposed_by = Column(String, nullable=False, default="model")  # model | harness | deterministic | user
    source_run_id = Column(String, nullable=True, index=True)
    namespace = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    content_json = Column(JSON, default=dict, nullable=False)
    source_type = Column(String, nullable=False, default="model_proposal")
    source_id = Column(String, nullable=True)
    source_hash = Column(String, nullable=False)
    proposed_ttl_seconds = Column(Integer, nullable=True)
    sensitivity = Column(String, nullable=False, default="low")  # low | high
    status = Column(String, nullable=False, default="pending", index=True)  # pending | auto_accepted | user_approved | rejected | expired
    decision_reason = Column(Text, nullable=True)
    decided_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    memory_id = Column(String, ForeignKey("user_memories.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


class MemoryAuditRecord(Base):
    """Immutable audit trail for every memory operation."""

    __tablename__ = "memory_audit_records"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)  # propose | auto_accept | approve | reject | write | read | update | delete | export | clear_namespace | disable_scope
    target_type = Column(String, nullable=False, default="memory")
    target_id = Column(String, nullable=True, index=True)
    namespace = Column(String, nullable=True, index=True)
    detail_json = Column(JSON, default=dict, nullable=False)
    actor = Column(String, nullable=False, default="system")
    trace_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


# -----------------------------------------------------------------------------
# Immutability enforcement (defense in depth, complements service-level rules)
# -----------------------------------------------------------------------------


def _prevent_evidence_snapshot_mutation(*_args, **_kwargs) -> None:
    raise RuntimeError("EvidenceSnapshot is immutable (INSERT-only)")


# The only columns a StrategyRelease may ever change are the review fields;
# the immutable strategy spec/hash/reference can never be mutated in place.
_STRATEGY_RELEASE_REVIEW_FIELDS = {"review_status", "reviewed_by_user_id", "reviewed_at", "review_notes"}


def _prevent_strategy_release_spec_mutation(mapper, _connection, target) -> None:
    from sqlalchemy.orm.attributes import get_history

    for attr in mapper.column_attrs:
        key = attr.key
        if key in _STRATEGY_RELEASE_REVIEW_FIELDS:
            continue
        if get_history(target, key).has_changes():
            raise RuntimeError(f"StrategyRelease.{key} is immutable")


event.listen(EvidenceSnapshot, "before_update", _prevent_evidence_snapshot_mutation)
event.listen(EvidenceSnapshot, "before_delete", _prevent_evidence_snapshot_mutation)


def _prevent_live_record_mutation(*_args, **_kwargs) -> None:
    raise RuntimeError("LIVE trading records are immutable (INSERT-only)")


event.listen(LedgerEntry, "before_update", _prevent_live_record_mutation)
event.listen(LedgerEntry, "before_delete", _prevent_live_record_mutation)
event.listen(RiskCheck, "before_update", _prevent_live_record_mutation)
event.listen(RiskCheck, "before_delete", _prevent_live_record_mutation)
event.listen(Fill, "before_update", _prevent_live_record_mutation)
event.listen(Fill, "before_delete", _prevent_live_record_mutation)
event.listen(TradingReconciliation, "before_update", _prevent_live_record_mutation)
event.listen(TradingReconciliation, "before_delete", _prevent_live_record_mutation)
event.listen(StrategyRelease, "before_update", _prevent_strategy_release_spec_mutation)
