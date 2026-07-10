from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


if "pytest" not in sys.modules:
    load_dotenv()


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./puregamma.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.getenv("SESSION_SECRET", os.getenv("JWT_SECRET", "dev-only-change-me"))
    auth_allow_demo_fallback: bool = os.getenv("AUTH_ALLOW_DEMO_FALLBACK", "false").lower() == "true"
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_oauth_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:3000/zh/auth/google/callback"))
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "pg_session")
    session_max_age_seconds: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "604800") or 604800)
    app_environment: str = os.getenv("APP_ENV", "development")

    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", os.getenv("LLM_MODEL", ""))
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", ""))
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    deepseek_thinking_mode: str = os.getenv("DEEPSEEK_THINKING_MODE", "disabled")
    deepseek_timeout_seconds: int = int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60") or 60)
    agent_provider: str = os.getenv("AGENT_PROVIDER", os.getenv("LLM_PROVIDER", ""))
    agent_model: str = os.getenv("AGENT_MODEL", os.getenv("LLM_MODEL", ""))
    agent_max_output_tokens: int = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "1200") or 1200)
    agent_temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.2") or 0.2)
    agent_request_timeout_ms: int = int(os.getenv("AGENT_REQUEST_TIMEOUT_MS", "60000") or 60000)
    agent_recent_messages: int = int(os.getenv("AGENT_RECENT_MESSAGES", "12") or 12)
    agent_max_context_chars: int = int(os.getenv("AGENT_MAX_CONTEXT_CHARS", "24000") or 24000)
    enable_mock_agent: bool = os.getenv("ENABLE_MOCK_AGENT", "false").lower() == "true"

    billing_mode: str = os.getenv("BILLING_MODE", "mock")
    billing_checkout_mode: str = os.getenv("BILLING_CHECKOUT_MODE", "session")
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_webhook_tolerance_seconds: int = int(os.getenv("STRIPE_WEBHOOK_TOLERANCE_SECONDS", "300") or 300)
    stripe_api_version: str = os.getenv("STRIPE_API_VERSION", "2026-02-25.clover")
    stripe_price_pro: str = os.getenv("STRIPE_PRICE_PRO", "price_mock_pro")
    stripe_price_max: str = os.getenv("STRIPE_PRICE_MAX", "price_mock_max")
    stripe_price_enterprise: str = os.getenv("STRIPE_PRICE_ENTERPRISE", "price_mock_enterprise")
    stripe_payment_link_primary: str = os.getenv("STRIPE_PAYMENT_LINK_PRIMARY", "https://buy.stripe.com/7sYbJ1dH6gLX2xq4EvcbC07")
    stripe_payment_link_pro: str = os.getenv("STRIPE_PAYMENT_LINK_PRO", "")
    stripe_payment_link_max: str = os.getenv("STRIPE_PAYMENT_LINK_MAX", "")
    stripe_payment_link_enterprise: str = os.getenv("STRIPE_PAYMENT_LINK_ENTERPRISE", "")
    stripe_success_url: str = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/billing/success")
    stripe_cancel_url: str = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/billing/cancel")

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587") or 587)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")

    massive_api_key: str = os.getenv("MASSIVE_API_KEY", "")
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    market_data_provider: str = os.getenv("MARKET_DATA_PROVIDER", "massive")
    enable_mock_market_data: bool = os.getenv("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true"

    imessage_provider: str = os.getenv("IMESSAGE_PROVIDER", "mock")
    imessage_relay_url: str = os.getenv("IMESSAGE_RELAY_URL", "http://localhost:8787")
    imessage_relay_secret: str = os.getenv("IMESSAGE_RELAY_SECRET", "")
    imessage_enabled_plans: tuple[str, ...] = tuple(_csv(os.getenv("IMESSAGE_ENABLED_PLANS", "Max,Enterprise")))
    imessage_max_message_length: int = int(os.getenv("IMESSAGE_MAX_MESSAGE_LENGTH", "3000") or 3000)
    imessage_rate_limit_per_user_per_day: int = int(os.getenv("IMESSAGE_RATE_LIMIT_PER_USER_PER_DAY", "20") or 20)

    market_data_mode: str = os.getenv("MARKET_DATA_MODE", "auto")
    market_snapshot_cache_ttl_seconds: int = int(os.getenv("MARKET_SNAPSHOT_CACHE_TTL_SECONDS", "15") or 15)
    binance_rest_base_url: str = os.getenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
    coinbase_rest_base_url: str = os.getenv("COINBASE_REST_BASE_URL", "https://api.exchange.coinbase.com")
    rss_sync_enabled: bool = os.getenv("RSS_SYNC_ENABLED", "true").lower() == "true"
    binance_public_data_enabled: bool = os.getenv("BINANCE_PUBLIC_DATA_ENABLED", "true").lower() == "true"
    defillama_free_enabled: bool = os.getenv("DEFILLAMA_FREE_ENABLED", "true").lower() == "true"
    the_graph_enabled: bool = os.getenv("THE_GRAPH_ENABLED", "true").lower() == "true"
    onchain_rpc_enabled: bool = os.getenv("ONCHAIN_RPC_ENABLED", "true").lower() == "true"
    enable_mock_data_sources: bool = os.getenv("ENABLE_MOCK_DATA_SOURCES", "false").lower() == "true"
    defillama_free_base_url: str = os.getenv("DEFILLAMA_FREE_BASE_URL", "https://api.llama.fi")
    defillama_pro_key: str = os.getenv("DEFILLAMA_PRO_KEY", "")
    defillama_max_response_bytes: int = int(os.getenv("DEFILLAMA_MAX_RESPONSE_BYTES", "30000000") or 30000000)
    rss_config_path: str = os.getenv("RSS_CONFIG_PATH", "config/rss_sources.yaml")
    rss_sync_interval: int = int(os.getenv("RSS_SYNC_INTERVAL", os.getenv("RSS_SYNC_INTERVAL_MINUTES", "15")) or 15)
    rss_request_timeout: float = float(os.getenv("RSS_REQUEST_TIMEOUT", "10") or 10)
    fintwit_config_path: str = os.getenv("FIN_TWIT_CONFIG_PATH", "config/fintwit_accounts.yaml")
    fintwit_sync_interval: int = int(os.getenv("FIN_TWIT_SYNC_INTERVAL", "30") or 30)
    x_api_key: str = os.getenv("X_API_KEY", "")
    x_api_secret: str = os.getenv("X_API_SECRET", "")
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    x_api_base_url: str = os.getenv("X_API_BASE_URL", "https://api.x.com/2")
    x_sync_interval: int = int(os.getenv("X_SYNC_INTERVAL", "30") or 30)
    x_search_query: str = os.getenv("X_SEARCH_QUERY", "(BTC OR ETH OR SOL OR HYPE) -is:retweet")
    x_list_id: str = os.getenv("X_LIST_ID", "")
    x_request_budget_per_sync: int = int(os.getenv("X_REQUEST_BUDGET_PER_SYNC", "4") or 4)
    bloomberg_mode: str = os.getenv("BLOOMBERG_MODE", "disabled").lower()
    bloomberg_api_url: str = os.getenv("BLOOMBERG_API_URL", "")
    bloomberg_api_key: str = os.getenv("BLOOMBERG_API_KEY", "")
    bloomberg_license_status: str = os.getenv("BLOOMBERG_LICENSE_STATUS", "unlicensed").lower()
    bloomberg_redistribution_allowed: bool = os.getenv("BLOOMBERG_REDISTRIBUTION_ALLOWED", "false").lower() == "true"
    data_retention_days: int = int(os.getenv("DATA_RETENTION_DAYS", "30") or 30)
    ethereum_rpc_url: str = os.getenv("ETHEREUM_RPC_URL", "")
    base_rpc_url: str = os.getenv("BASE_RPC_URL", "")
    arbitrum_rpc_url: str = os.getenv("ARBITRUM_RPC_URL", "")
    bsc_rpc_url: str = os.getenv("BSC_RPC_URL", "")
    polygon_rpc_url: str = os.getenv("POLYGON_RPC_URL", "")
    data_sync_worker_enabled: bool = os.getenv("DATA_SYNC_WORKER_ENABLED", "true").lower() == "true"
    rss_sync_interval_minutes: int = int(os.getenv("RSS_SYNC_INTERVAL_MINUTES", "15") or 15)
    binance_sync_interval_minutes: int = int(os.getenv("BINANCE_SYNC_INTERVAL_MINUTES", "2") or 2)
    defillama_sync_interval_minutes: int = int(os.getenv("DEFILLAMA_SYNC_INTERVAL_MINUTES", "180") or 180)
    onchain_sync_interval_minutes: int = int(os.getenv("ONCHAIN_SYNC_INTERVAL_MINUTES", "15") or 15)
    provider_http_timeout_seconds: float = float(os.getenv("PROVIDER_HTTP_TIMEOUT_SECONDS", "10") or 10)
    provider_max_response_bytes: int = int(os.getenv("PROVIDER_MAX_RESPONSE_BYTES", "5000000") or 5000000)

    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")

    @property
    def rpc_urls(self) -> dict[str, str]:
        return {
            "ethereum": self.ethereum_rpc_url,
            "base": self.base_rpc_url,
            "arbitrum": self.arbitrum_rpc_url,
            "bsc": self.bsc_rpc_url,
            "polygon": self.polygon_rpc_url,
        }

    @property
    def stripe_price_by_plan(self) -> dict[str, str]:
        return {
            "Pro": self.stripe_price_pro,
            "Max": self.stripe_price_max,
            "Enterprise": self.stripe_price_enterprise,
        }

    @property
    def stripe_payment_link_by_plan(self) -> dict[str, str]:
        return {
            "Pro": self.stripe_payment_link_pro,
            "Max": self.stripe_payment_link_max,
            "Enterprise": self.stripe_payment_link_enterprise,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
