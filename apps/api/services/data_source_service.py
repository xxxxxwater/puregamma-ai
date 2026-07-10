from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.data.binance_provider import BinanceProvider
from packages.data.bloomberg_provider import BloombergProvider
from packages.data.defillama_provider import DefiLlamaProvider
from packages.data.fintwit_provider import FinTwitAccountConfig, FinTwitProvider
from packages.data.onchain_provider import EVMRPCProvider
from packages.data.provider import DataSourceStatus, ProviderError
from packages.data.rss_provider import RSSProvider
from packages.data.subgraph_provider import SubgraphProvider
from packages.data.x_twitter_provider import XTwitterProvider
from packages.database.models import DataSource, DataSourceSyncRun, DefiMetric, FinTwitAccount, MarketQuoteRecord, NewsItem, NormalizedDocument, OnchainMetric, ProviderSyncLog, RawDocument, Source, utcnow
from apps.api.services.document_pipeline_service import run_document_pipeline


SOURCE_DEFINITIONS = (
    ("rss", "RSS News", "news", "rss", True),
    ("fintwit", "FinTwit Curated Opinion Flow", "opinion", "fintwit", True),
    ("x-twitter", "X / Twitter Official API", "opinion", "x", True),
    ("bloomberg", "Bloomberg Authorized Data", "licensed_news", "bloomberg", True),
    ("binance", "Binance Public Market Data", "market", "binance", True),
    ("defillama-free", "DefiLlama Free", "defi", "defillama", True),
    ("the-graph", "The Graph", "onchain", "the-graph", True),
    ("evm-rpc", "EVM RPC", "onchain", "evm-rpc", True),
    ("coinglass", "CoinGlass", "market", "coinglass", False),
    ("glassnode", "Glassnode", "onchain", "glassnode", False),
    ("plaid", "Plaid", "portfolio", "plaid", False),
    ("exchange-account", "Exchange account", "portfolio", "exchange", False),
    ("wallet", "Wallet", "portfolio", "wallet", False),
)

DOCUMENT_PROVIDER_IDS = {"rss", "fintwit", "x-twitter", "bloomberg"}


def redact_error(value: str | None) -> str | None:
    if not value:
        return value
    value = re.sub(r"(?i)(api[_-]?key|token|secret|authorization)=?[^\s,;]+", r"\1=[REDACTED]", value)
    value = re.sub(r"https://[^\s/@]+@", "https://[REDACTED]@", value)
    return value[:500]


def seed_data_sources(db: Session) -> None:
    settings = get_settings()
    optional_status = {
        "fintwit": FinTwitProvider().health_check().status.value,
        "x-twitter": XTwitterProvider().health_check().status.value,
        "bloomberg": BloombergProvider().health_check().status.value,
        "coinglass": DataSourceStatus.HEALTHY.value if bool(__import__("os").getenv("COINGLASS_API_KEY")) else DataSourceStatus.NEED_KEY.value,
        "glassnode": DataSourceStatus.HEALTHY.value if bool(__import__("os").getenv("GLASSNODE_API_KEY")) else DataSourceStatus.NEED_KEY.value,
        "plaid": DataSourceStatus.NEED_KEY.value if bool(__import__("os").getenv("PLAID_CLIENT_ID")) is False else DataSourceStatus.NOT_CONNECTED.value,
        "exchange-account": DataSourceStatus.NOT_CONNECTED.value,
        "wallet": DataSourceStatus.NOT_CONNECTED.value,
    }
    enabled_map = {
        "rss": settings.rss_sync_enabled,
        "fintwit": True,
        "x-twitter": True,
        "bloomberg": settings.bloomberg_mode in {"mock", "production"},
        "binance": settings.binance_public_data_enabled,
        "defillama-free": settings.defillama_free_enabled,
        "the-graph": settings.the_graph_enabled,
        "evm-rpc": settings.onchain_rpc_enabled,
    }
    for source_id, name, category, provider, syncable in SOURCE_DEFINITIONS:
        row = db.get(DataSource, source_id) or DataSource(id=source_id)
        row.name = name
        row.category = category
        row.provider = provider
        row.enabled = enabled_map.get(source_id, syncable)
        metadata = dict(row.metadata_json or {})
        metadata["primary"] = source_id in DOCUMENT_PROVIDER_IDS
        metadata["retentionDays"] = settings.data_retention_days
        if source_id == "fintwit":
            metadata["accountCount"] = len(FinTwitProvider.load_accounts(settings.fintwit_config_path))
            metadata["licenseStatus"] = "official-api-or-authorized-feed-only"
        elif source_id == "x-twitter":
            metadata["licenseStatus"] = "x-developer-agreement"
            metadata["retentionPolicy"] = "X policy plus configured retention"
        elif source_id == "bloomberg":
            metadata["licenseStatus"] = settings.bloomberg_license_status
            metadata["retentionPolicy"] = "commercial-contract-defined"
        elif source_id == "rss":
            metadata["licenseStatus"] = "per-feed configuration"
        row.metadata_json = metadata
        if source_id in optional_status:
            row.status = optional_status[source_id]
        elif not row.enabled:
            row.status = DataSourceStatus.DISABLED.value
        db.add(row)
    _seed_fintwit_accounts(db)
    db.commit()


def provider_registry(db: Session | None = None) -> dict[str, object]:
    rss_metadata = dict((db.get(DataSource, "rss").metadata_json or {})) if db and db.get(DataSource, "rss") else {}
    account_configs: list[FinTwitAccountConfig] | None = None
    if db:
        account_configs = [FinTwitAccountConfig(username=row.username, display_name=row.display_name, platform=row.platform, category=row.category, language=row.language, credibility_score=row.credibility_score, account_weight=row.account_weight, enabled=row.enabled, source_url=row.source_url or "", provider_user_id=row.provider_user_id, collection_method=row.collection_method) for row in db.query(FinTwitAccount).all()]
    x_provider = XTwitterProvider()
    return {
        "rss": RSSProvider(validators=rss_metadata.get("validators") or {}),
        "fintwit": FinTwitProvider(accounts=account_configs, x_provider=x_provider),
        "x-twitter": x_provider,
        "bloomberg": BloombergProvider(),
        "binance": BinanceProvider(),
        "defillama-free": DefiLlamaProvider(),
        "the-graph": SubgraphProvider(),
        "evm-rpc": EVMRPCProvider(),
    }


def _seed_fintwit_accounts(db: Session) -> None:
    for account in FinTwitProvider.load_accounts(get_settings().fintwit_config_path):
        row = db.query(FinTwitAccount).filter_by(platform=account.platform, username=account.username).one_or_none() or FinTwitAccount(username=account.username, platform=account.platform)
        row.display_name = account.display_name
        row.category = account.category
        row.language = account.language
        row.credibility_score = account.credibility_score
        row.account_weight = account.account_weight
        row.enabled = account.enabled
        row.source_url = account.source_url
        row.provider_user_id = account.provider_user_id
        row.collection_method = account.collection_method
        db.add(row)


def _persist_news(db: Session, records: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for record in records:
        row = db.query(NewsItem).filter((NewsItem.content_hash == record["content_hash"]) | (NewsItem.canonical_url == record["canonical_url"])).first()
        if row:
            row.summary = record["summary"] or row.summary
            row.fetched_at = record["fetched_at"]
            row.sentiment_score = Decimal(str(record["sentiment_score"]))
            row.sentiment_label = record["sentiment_label"]
            row.related_symbols = record["related_symbols"]
            row.provenance_json = record["provenance_json"]
            updated += 1
        else:
            db.add(NewsItem(**record))
            inserted += 1
    return inserted, updated


def _persist_market(db: Session, records: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for record in records:
        row = db.query(MarketQuoteRecord).filter_by(provider=record["provider"], symbol=record["symbol"], source_timestamp=record["source_timestamp"]).one_or_none()
        if row:
            for key, value in record.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(MarketQuoteRecord(**record))
            inserted += 1
    return inserted, updated


def _persist_defi(db: Session, records: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for record in records:
        row = db.query(DefiMetric).filter_by(entity_type=record["entity_type"], entity_id=record["entity_id"], chain=record["chain"], metric_type=record["metric_type"]).one_or_none()
        if row:
            for key, value in record.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(DefiMetric(**record))
            inserted += 1
    return inserted, updated


def _persist_onchain(db: Session, records: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for record in records:
        row = db.query(OnchainMetric).filter_by(provider=record["provider"], chain=record["chain"], entity_id=record["entity_id"], metric_type=record["metric_type"]).one_or_none()
        if row:
            for key, value in record.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(OnchainMetric(**record))
            inserted += 1
    return inserted, updated


def _persist_subgraph(db: Session, records: list[dict]) -> tuple[int, int]:
    normalized = []
    fetched_at = utcnow()
    for record in records:
        config, data = record["config"], record["data"]
        for external_key, metric_type in (("totalValueLockedUSD", "tvl_usd"), ("volumeUSD", "volume_usd"), ("txCount", "tx_count"), ("totalBorrowBalanceUSD", "borrow_usd")):
            if data.get(external_key) is not None:
                normalized.append({"provider": "the-graph", "chain": config.chain, "entity_id": data["id"], "metric_type": metric_type, "value": str(data[external_key]), "block_number": None, "source_timestamp": None, "fetched_at": fetched_at, "provenance_json": {"provider": "the-graph", "fetchedAt": fetched_at.isoformat(), "isMock": False, "isFallback": False}})
    return _persist_onchain(db, normalized)


PERSISTERS = {"rss": _persist_news, "binance": _persist_market, "defillama-free": _persist_defi, "evm-rpc": _persist_onchain, "the-graph": _persist_subgraph}


def sync_provider(db: Session, provider_id: str, *, force: bool = False):
    source = db.get(DataSource, provider_id)
    if not source:
        raise ValueError(f"Unknown provider: {provider_id}")
    if not source.enabled:
        raise ValueError(f"Provider is disabled: {provider_id}")
    registry = provider_registry(db)
    provider = registry.get(provider_id)
    if not provider:
        raise ValueError(f"Provider is not syncable: {provider_id}")
    if provider_id in DOCUMENT_PROVIDER_IDS:
        return run_document_pipeline(db, source, provider, force=force)
    recent = db.query(DataSourceSyncRun).filter(DataSourceSyncRun.provider_id == provider_id, DataSourceSyncRun.status == "RUNNING", DataSourceSyncRun.started_at > utcnow() - timedelta(minutes=15)).first()
    if recent:
        return recent
    bucket = int(utcnow().timestamp() // (10 if force else 60))
    run = DataSourceSyncRun(provider_id=provider_id, trace_id=str(uuid.uuid4()), idempotency_key=f"{provider_id}:{bucket}", status="RUNNING")
    db.add(run)
    source.last_sync_at = utcnow()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.query(DataSourceSyncRun).filter_by(provider_id=provider_id, idempotency_key=f"{provider_id}:{bucket}").one()
    try:
        result = provider.sync()
        inserted, updated = PERSISTERS[provider_id](db, result.records)
        db.flush()
        run.fetched_count = result.fetched_count
        run.inserted_count = inserted
        run.updated_count = updated
        run.status = result.status.value
        run.error_message = redact_error("; ".join(result.errors)) or None
        source.status = result.status.value
        source.last_error = run.error_message
        source.item_count = _source_count(db, provider_id)
        if result.status in {DataSourceStatus.HEALTHY, DataSourceStatus.PARTIAL}:
            source.last_success_at = utcnow()
    except Exception as exc:
        status = DataSourceStatus.RATE_LIMITED if isinstance(exc, ProviderError) and exc.code == "rate_limited" else DataSourceStatus.ERROR
        run.status = status.value
        run.error_message = redact_error(str(exc))
        source.status = status.value
        source.last_error = run.error_message
    run.completed_at = utcnow()
    db.commit()
    db.refresh(run)
    return run


def sync_all_providers(db: Session) -> list[DataSourceSyncRun]:
    runs = []
    for provider_id in ("rss", "fintwit", "x-twitter", "bloomberg"):
        source = db.get(DataSource, provider_id)
        if source and source.enabled:
            try:
                runs.append(sync_provider(db, provider_id))
            except Exception:
                db.rollback()
    return runs


def _source_count(db: Session, provider_id: str) -> int:
    if provider_id in DOCUMENT_PROVIDER_IDS:
        return int(db.query(func.count(NormalizedDocument.id)).filter(NormalizedDocument.provider == provider_id).scalar() or 0)
    model = {"rss": NewsItem, "binance": MarketQuoteRecord, "defillama-free": DefiMetric, "evm-rpc": OnchainMetric, "the-graph": OnchainMetric}.get(provider_id)
    if not model:
        return 0
    query = db.query(func.count(model.id))
    if provider_id == "binance":
        query = query.filter(MarketQuoteRecord.provider == "binance")
    if provider_id == "evm-rpc":
        query = query.filter(OnchainMetric.provider == "evm-rpc")
    if provider_id == "the-graph":
        query = query.filter(OnchainMetric.provider == "the-graph")
    return int(query.scalar() or 0)


def serialize_source(row: DataSource) -> dict:
    metadata = row.metadata_json or {}
    usage = metadata.get("usage") or {}
    return {
        "id": row.id,
        "source": row.name,
        "type": row.category,
        "provider": row.provider,
        "status": row.status,
        "requiredPlan": "Free" if row.id == "rss" else "Max" if row.id in {"fintwit", "x-twitter", "bloomberg"} else "Extension",
        "lastSync": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "lastSuccess": row.last_success_at.isoformat() if row.last_success_at else None,
        "error": redact_error(row.last_error) or "",
        "itemsIngested": row.item_count,
        "enabled": row.enabled,
        "primary": bool(metadata.get("primary")),
        "configured": row.status not in {DataSourceStatus.NEEDS_KEY.value, DataSourceStatus.NEED_KEY.value, DataSourceStatus.LICENSE_REQUIRED.value, DataSourceStatus.NOT_LICENSED.value},
        "quotaLimit": usage.get("quotaLimit"),
        "quotaRemaining": usage.get("quotaRemaining"),
        "rateLimitResetAt": usage.get("rateLimitResetAt"),
        "requestCount": usage.get("requests", 0),
        "errorCount": int(metadata.get("failureCount", 0)),
        "circuitOpenUntil": metadata.get("circuitOpenUntil"),
        "retentionPolicy": metadata.get("retentionPolicy") or f"{metadata.get('retentionDays', 30)} days",
        "licenseStatus": metadata.get("licenseStatus") or ("configuration-defined" if row.id == "rss" else "provider-policy"),
        "accountCount": metadata.get("accountCount", 0),
    }


def serialize_run(row) -> dict:
    return {"id": row.id, "provider_id": row.provider_id, "status": row.status, "trace_id": getattr(row, "trace_id", row.id), "fetched_count": row.fetched_count, "inserted_count": row.inserted_count, "updated_count": getattr(row, "updated_count", 0), "duplicate_count": getattr(row, "duplicate_count", 0), "error": getattr(row, "error_message", None), "started_at": row.started_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None}
