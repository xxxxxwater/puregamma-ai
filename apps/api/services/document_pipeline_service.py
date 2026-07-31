from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from packages.data.enrichment import engagement_score, event_fingerprint, extract_symbols, freshness_score, stable_hash, weighted_sentiment
from packages.data.provider import DataProvider, DataSourceStatus, ProviderDocument, ProviderError, ProviderFetchResult
from packages.database.models import DataSource, EntityMention, NormalizedDocument, ProviderSyncLog, RawDocument, SentimentSignal, Source, utcnow


CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RECOVERY_MINUTES = 15


def run_document_pipeline(db: Session, data_source: DataSource, provider: DataProvider, *, force: bool = False) -> ProviderSyncLog:
    metadata = dict(data_source.metadata_json or {})
    _ensure_circuit_available(metadata, force=force)
    bucket = int(utcnow().timestamp() // (10 if force else 60))
    log = ProviderSyncLog(provider_id=data_source.id, status="RUNNING", idempotency_key=f"{data_source.id}:{bucket}", cursor_before=metadata.get("cursor"))
    db.add(log)
    data_source.last_sync_at = utcnow()
    try:
        fetched = provider.fetch_since(metadata.get("cursor"))
        documents = provider.deduplicate(provider.normalize(fetched.documents))
        inserted, duplicates = persist_documents(db, data_source.id, documents)
        health = provider.health_check()
        status = _success_status(health.status, fetched)
        log.status = status.value
        log.cursor_after = fetched.next_cursor or metadata.get("cursor")
        log.fetched_count = len(fetched.documents)
        log.inserted_count = inserted
        log.duplicate_count = duplicates
        log.http_status = fetched.http_status
        log.retry_count = provider.get_usage().retries
        log.rate_limit_reset_at = provider.get_usage().rate_limit_reset_at
        log.usage_json = provider.get_usage().as_dict()
        log.error_message = "; ".join(fetched.errors)[:500] or None
        metadata.update({"cursor": log.cursor_after, "usage": log.usage_json, "lastHttpStatus": fetched.http_status, "failureCount": 0, "circuitOpenUntil": None})
        validators = getattr(provider, "validators", None)
        if validators is not None:
            metadata["validators"] = validators
        data_source.status = status.value
        data_source.last_error = log.error_message
        data_source.item_count = db.query(NormalizedDocument).filter(NormalizedDocument.provider == data_source.id).count()
        data_source.last_success_at = utcnow()
    except Exception as exc:
        _record_failure(data_source, metadata, log, exc)
    log.completed_at = utcnow()
    data_source.metadata_json = metadata
    db.commit()
    db.refresh(log)
    return log


def persist_documents(db: Session, provider_id: str, documents: list[ProviderDocument]) -> tuple[int, int]:
    inserted = 0
    duplicates = 0
    for item in documents:
        content_digest = stable_hash(item.title, item.content or item.summary, item.url)
        existing = db.query(RawDocument).filter(or_(
            (RawDocument.provider == provider_id) & (RawDocument.external_id == item.external_id),
            RawDocument.content_hash == content_digest,
        )).first()
        if existing:
            duplicates += 1
            continue
        source = _source_for(db, provider_id, item)
        raw = RawDocument(source_id=source.id, provider=provider_id, external_id=item.external_id, cursor=item.cursor, content_hash=content_digest, raw_payload=item.raw_payload, source_url=item.url, published_at=_utc(item.published_at), fetched_at=_utc(item.fetched_at), license_status=item.license_status, retention_policy=item.retention_policy, processing_status="normalized")
        db.add(raw)
        db.flush()
        symbols = item.symbols or extract_symbols(f"{item.title} {item.content} {item.summary}")
        fingerprint = event_fingerprint(item.title, symbols, item.published_at)
        same_event_count = db.query(NormalizedDocument).filter(NormalizedDocument.event_fingerprint == fingerprint).count()
        sentiment_value = float(item.sentiment.get("score", 0) or 0)
        freshness = freshness_score(item.published_at)
        engagement = engagement_score(item.engagement_metrics)
        relevance = 1.0 if symbols else 0.2
        final = weighted_sentiment(sentiment_value, item.credibility_score, freshness, engagement, relevance)
        final /= 1.0 + (0.35 * same_event_count)
        normalized = NormalizedDocument(raw_document_id=raw.id, source_id=source.id, provider=provider_id, source_type=item.source_type, source_name=item.source_name, title=item.title, content=item.content, summary=item.summary, url=item.url, author=item.author or None, published_at=_utc(item.published_at), language=item.language, symbols=symbols, topics=item.topics, sentiment=item.sentiment, credibility_score=item.credibility_score, engagement_metrics=item.engagement_metrics, raw_payload=item.raw_payload, license_status=item.license_status, retention_policy=item.retention_policy, redistribution_allowed=item.redistribution_allowed, stable_hash=content_digest, event_fingerprint=fingerprint, final_score=final)
        db.add(normalized)
        db.flush()
        for symbol in symbols:
            db.add(EntityMention(document_id=normalized.id, symbol=symbol, mention_text=symbol, relevance_score=relevance))
        db.add(SentimentSignal(document_id=normalized.id, sentiment_score=sentiment_value, sentiment_label=str(item.sentiment.get("label", "neutral")), source_credibility=item.credibility_score, freshness_score=freshness, engagement_score=engagement, asset_relevance=relevance, final_score=final, event_fingerprint=fingerprint))
        inserted += 1
    return inserted, duplicates


def aggregate_events(db: Session, *, hours: int = 72, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    cutoff = utcnow() - timedelta(hours=max(1, min(hours, 720)))
    rows = db.query(NormalizedDocument).filter(NormalizedDocument.created_at >= cutoff).order_by(NormalizedDocument.published_at.desc(), NormalizedDocument.created_at.desc()).limit(500).all()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        if symbol and symbol.upper() not in (row.symbols or []):
            continue
        group = groups.setdefault(row.event_fingerprint, {"eventFingerprint": row.event_fingerprint, "title": row.title, "symbols": row.symbols, "topics": row.topics, "score": 0.0, "sources": [], "publishedAt": row.published_at.isoformat() if row.published_at else None})
        group["score"] += row.final_score
        if not any(item["provider"] == row.provider and item["url"] == row.url for item in group["sources"]):
            group["sources"].append({"provider": row.provider, "source": row.source_name, "url": row.url, "author": row.author})
    return sorted(groups.values(), key=lambda item: (len(item["sources"]), abs(item["score"])), reverse=True)[:limit]


def _source_for(db: Session, provider_id: str, item: ProviderDocument) -> Source:
    external_key = item.source_name.lower().replace(" ", "-")[:180]
    source = db.query(Source).filter_by(provider=provider_id, external_key=external_key).one_or_none()
    if not source:
        source = Source(provider=provider_id, provider_type=item.source_type, external_key=external_key, name=item.source_name, source_url=item.url, language=item.language, credibility_score=item.credibility_score, source_license=item.license_status, redistribution_allowed=item.redistribution_allowed, retention_policy=item.retention_policy, config_json={})
        db.add(source)
        db.flush()
    return source


def _success_status(health: DataSourceStatus, fetched: ProviderFetchResult) -> DataSourceStatus:
    if fetched.errors and fetched.documents:
        return DataSourceStatus.DEGRADED
    if fetched.errors:
        return DataSourceStatus.ERROR
    return health


def _ensure_circuit_available(metadata: dict, *, force: bool) -> None:
    value = metadata.get("circuitOpenUntil")
    if not value or force:
        return
    open_until = datetime.fromisoformat(value)
    if _utc(open_until) > utcnow():
        raise ProviderError("circuit_open", f"Provider circuit is open until {value}")


def _record_failure(data_source: DataSource, metadata: dict, log: ProviderSyncLog, exc: Exception) -> None:
    status = DataSourceStatus.DEGRADED
    code = "provider_error"
    http_status = None
    if isinstance(exc, ProviderError):
        code = exc.code
        http_status = exc.status_code
        if exc.code == "needs_key":
            status = DataSourceStatus.NEEDS_KEY
        elif exc.code in {"license_required", "not_licensed"}:
            status = DataSourceStatus.LICENSE_REQUIRED
        elif exc.code == "rate_limited":
            status = DataSourceStatus.DEGRADED
    failures = int(metadata.get("failureCount", 0)) + 1
    metadata["failureCount"] = failures
    if failures >= CIRCUIT_FAILURE_THRESHOLD:
        metadata["circuitOpenUntil"] = (utcnow() + timedelta(minutes=CIRCUIT_RECOVERY_MINUTES)).isoformat()
    message = str(exc)[:500]
    log.status = status.value
    log.error_code = code
    log.error_message = message
    log.http_status = http_status
    data_source.status = status.value
    data_source.last_error = message


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
