from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from packages.database.models import GatewayApiKey, GatewayRequestLog


def _dialect_name(db: Session) -> str:
    return (db.bind.dialect.name if db.bind is not None else "sqlite").lower()


def _bucket_expression(db: Session, granularity: str):
    """Return a dialect-aware SQL expression that truncates created_at to the
    requested granularity. PostgreSQL uses date_trunc; SQLite uses strftime."""
    if _dialect_name(db) == "postgresql":
        return func.date_trunc(granularity, GatewayRequestLog.created_at)
    fmt = "%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d"
    return func.strftime(fmt, GatewayRequestLog.created_at)


def _bucket_datetime(bucket, granularity: str) -> datetime:
    """Normalize a raw bucket value (timestamp on PostgreSQL, string on SQLite)
    to an aware UTC datetime."""
    if isinstance(bucket, datetime):
        value = bucket
    else:
        value = datetime.strptime(str(bucket), "%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _bucket_key(bucket, granularity: str) -> str:
    return _bucket_datetime(bucket, granularity).isoformat()


def _iter_buckets(start: datetime, end: datetime, granularity: str):
    if granularity == "hour":
        step = timedelta(hours=1)
    else:
        step = timedelta(days=1)
    current = start
    while current <= end:
        yield current
        current += step


def _row_to_bucket(row, granularity: str) -> dict[str, Any]:
    requests = int(row.requests or 0)
    success = int(row.success or 0)
    return {
        "bucket": _bucket_key(row.bucket, granularity),
        "requests": requests,
        "success": success,
        "errors": requests - success,
        "input_tokens": int(row.input_tokens or 0),
        "output_tokens": int(row.output_tokens or 0),
        "cache_tokens": int(row.cache_tokens or 0),
        "reasoning_tokens": int(row.reasoning_tokens or 0),
        "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
        "max_latency_ms": int(row.max_latency_ms or 0),
        "cost_usd": str(Decimal(str(row.cost_usd or 0))),
    }


def _empty_bucket(bucket: datetime, granularity: str) -> dict[str, Any]:
    return {
        "bucket": bucket.isoformat(),
        "requests": 0,
        "success": 0,
        "errors": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "reasoning_tokens": 0,
        "avg_latency_ms": 0.0,
        "max_latency_ms": 0,
        "cost_usd": "0",
    }


def _aggregate_rows(rows) -> dict[str, Any]:
    requests = sum(int(row.requests or 0) for row in rows)
    success = sum(int(row.success or 0) for row in rows)
    latencies = [float(row.avg_latency_ms or 0) for row in rows if int(row.requests or 0) > 0]
    return {
        "requests": requests,
        "success": success,
        "errors": requests - success,
        "input_tokens": sum(int(row.input_tokens or 0) for row in rows),
        "output_tokens": sum(int(row.output_tokens or 0) for row in rows),
        "cache_tokens": sum(int(row.cache_tokens or 0) for row in rows),
        "reasoning_tokens": sum(int(row.reasoning_tokens or 0) for row in rows),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "max_latency_ms": max((int(row.max_latency_ms or 0) for row in rows), default=0),
        "cost_usd": str(sum((Decimal(str(row.cost_usd or 0)) for row in rows), Decimal("0"))),
    }


def usage_summary(
    db: Session,
    user_id: str | None,
    start: datetime,
    end: datetime,
    granularity: str,
    model: str | None = None,
    api_key_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate GatewayRequestLog into a zero-filled time series plus totals
    and per-model / per-key breakdowns.

    ``user_id`` scopes the aggregation to one user; ``None`` aggregates across
    every user (used by the administrator console)."""
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    def _filters(query):
        if user_id is not None:
            query = query.filter(GatewayRequestLog.user_id == user_id)
        query = query.filter(
            GatewayRequestLog.created_at >= start,
            GatewayRequestLog.created_at < end,
        )
        if model:
            query = query.filter(GatewayRequestLog.public_model == model)
        if api_key_id:
            query = query.filter(GatewayRequestLog.api_key_id == api_key_id)
        return query

    bucket_expr = _bucket_expression(db, granularity)
    success_expr = func.sum(case((GatewayRequestLog.status == "success", 1), else_=0)).label("success")

    bucket_rows = (
        _filters(db.query(bucket_expr.label("bucket")))
        .with_entities(
            bucket_expr.label("bucket"),
            func.count(GatewayRequestLog.id).label("requests"),
            success_expr,
            func.coalesce(func.sum(GatewayRequestLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.cache_tokens), 0).label("cache_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.reasoning_tokens), 0).label("reasoning_tokens"),
            func.coalesce(func.avg(GatewayRequestLog.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.max(GatewayRequestLog.latency_ms), 0).label("max_latency_ms"),
            func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0).label("cost_usd"),
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr)
        .all()
    )

    filled: dict[str, dict[str, Any]] = {}
    for bucket in _iter_buckets(start, end, granularity):
        filled[bucket.isoformat()] = _empty_bucket(bucket, granularity)
    for row in bucket_rows:
        filled[_bucket_key(row.bucket, granularity)] = _row_to_bucket(row, granularity)

    totals_rows = (
        _filters(db.query(GatewayRequestLog))
        .with_entities(
            func.count(GatewayRequestLog.id).label("requests"),
            success_expr,
            func.coalesce(func.sum(GatewayRequestLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.cache_tokens), 0).label("cache_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.reasoning_tokens), 0).label("reasoning_tokens"),
            func.coalesce(func.avg(GatewayRequestLog.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.max(GatewayRequestLog.latency_ms), 0).label("max_latency_ms"),
            func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0).label("cost_usd"),
        )
        .all()
    )

    model_rows = (
        _filters(db.query(GatewayRequestLog))
        .with_entities(
            GatewayRequestLog.public_model.label("model"),
            func.count(GatewayRequestLog.id).label("requests"),
            success_expr,
            func.coalesce(func.sum(GatewayRequestLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.cache_tokens), 0).label("cache_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.reasoning_tokens), 0).label("reasoning_tokens"),
            func.coalesce(func.avg(GatewayRequestLog.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0).label("cost_usd"),
        )
        .group_by(GatewayRequestLog.public_model)
        .order_by(func.sum(GatewayRequestLog.retail_cost_usd).desc())
        .all()
    )

    key_rows = (
        _filters(db.query(GatewayRequestLog))
        .with_entities(
            GatewayRequestLog.api_key_id.label("api_key_id"),
            func.count(GatewayRequestLog.id).label("requests"),
            success_expr,
            func.coalesce(func.sum(GatewayRequestLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(GatewayRequestLog.cache_tokens), 0).label("cache_tokens"),
            func.coalesce(func.avg(GatewayRequestLog.latency_ms), 0).label("avg_latency_ms"),
            func.coalesce(func.sum(GatewayRequestLog.retail_cost_usd), 0).label("cost_usd"),
        )
        .group_by(GatewayRequestLog.api_key_id)
        .order_by(func.sum(GatewayRequestLog.retail_cost_usd).desc())
        .all()
    )
    key_query = db.query(GatewayApiKey)
    if user_id is not None:
        key_query = key_query.filter(GatewayApiKey.user_id == user_id)
    key_names = {
        row.id: {"name": row.name, "prefix": row.key_hint}
        for row in key_query.all()
    }

    def _model_row(row) -> dict[str, Any]:
        requests = int(row.requests or 0)
        return {
            "model": row.model,
            "requests": requests,
            "success": int(row.success or 0),
            "errors": requests - int(row.success or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "cache_tokens": int(row.cache_tokens or 0),
            "reasoning_tokens": int(row.reasoning_tokens or 0),
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
            "cost_usd": str(Decimal(str(row.cost_usd or 0))),
        }

    def _key_row(row) -> dict[str, Any]:
        requests = int(row.requests or 0)
        info = key_names.get(row.api_key_id) or {}
        return {
            "api_key_id": row.api_key_id,
            "name": info.get("name") or "deleted key",
            "prefix": info.get("prefix") or "",
            "requests": requests,
            "success": int(row.success or 0),
            "errors": requests - int(row.success or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "cache_tokens": int(row.cache_tokens or 0),
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 2),
            "cost_usd": str(Decimal(str(row.cost_usd or 0))),
        }

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": granularity,
        "buckets": list(filled.values()),
        "totals": _aggregate_rows(totals_rows),
        "by_model": [_model_row(row) for row in model_rows],
        "by_key": [_key_row(row) for row in key_rows],
    }
