from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

from packages.database.models import DataSource, NormalizedDocument, utcnow


NewsKind = Literal["all", "flash", "article"]
NewsSource = Literal["all", "chaincatcher", "rss"]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    aware = _utc(value)
    return aware.astimezone(timezone.utc).isoformat() if aware else None


def _encode_cursor(sort_at: datetime, document_id: str) -> str:
    payload = json.dumps(
        {"at": _iso(sort_at), "id": document_id}, separators=(",", ":"), sort_keys=True
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        timestamp = datetime.fromisoformat(str(payload["at"]).replace("Z", "+00:00"))
        document_id = str(payload["id"])
        if not document_id or len(document_id) > 128:
            return None
        return _utc(timestamp) or timestamp, document_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _providers(source: NewsSource) -> tuple[str, ...]:
    if source == "chaincatcher":
        return ("chaincatcher",)
    if source == "rss":
        return ("rss",)
    return ("chaincatcher", "rss")


def _kind(row: NormalizedDocument) -> str:
    raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    value = str(raw.get("content_type") or "").lower()
    if value in {"flash", "article"}:
        return value
    return "flash" if row.source_type == "flash_news" else "article"


def _serialize(row: NormalizedDocument, now: datetime) -> dict[str, Any]:
    raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    published_at = _utc(row.published_at) or _utc(row.created_at) or now
    thumbnail = raw.get("thumbnail")
    if not isinstance(thumbnail, str) or not thumbnail.startswith("https://"):
        thumbnail = None
    keywords = raw.get("keywords") if isinstance(raw.get("keywords"), list) else []
    original = raw.get("original") if isinstance(raw.get("original"), bool) else None
    return {
        "id": row.id,
        "provider": row.provider,
        "source": row.source_name,
        "kind": _kind(row),
        "title": row.title,
        "summary": (row.summary or "")[:600],
        "url": row.url,
        "language": row.language,
        "published_at": _iso(published_at),
        "fetched_at": _iso(row.created_at),
        "age_seconds": max(0, int((now - published_at).total_seconds())),
        "symbols": list(row.symbols or [])[:20],
        "topics": list(row.topics or [])[:20],
        "keywords": [str(value) for value in keywords[:20]],
        "sentiment": row.sentiment or {},
        "original": original,
        "thumbnail": thumbnail,
        "attribution": "ChainCatcher" if row.provider == "chaincatcher" else row.source_name,
        "license_status": row.license_status,
        "redistribution_allowed": bool(row.redistribution_allowed),
    }


def list_news_feed(
    db: Session,
    *,
    kind: NewsKind = "flash",
    source: NewsSource = "chaincatcher",
    language: str | None = None,
    symbol: str | None = None,
    query_text: str | None = None,
    hours: int = 72,
    limit: int = 30,
    cursor: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    hours = max(1, min(hours, 168))
    limit = max(1, min(limit, 50))
    sort_at = func.coalesce(NormalizedDocument.published_at, NormalizedDocument.created_at)
    query = db.query(NormalizedDocument).filter(
        NormalizedDocument.provider.in_(_providers(source)),
        sort_at >= now - timedelta(hours=hours),
    )
    if kind == "flash":
        query = query.filter(NormalizedDocument.source_type == "flash_news")
    elif kind == "article":
        query = query.filter(NormalizedDocument.source_type != "flash_news")
    if symbol:
        normalized_symbol = symbol.strip().upper()
        query = query.filter(cast(NormalizedDocument.symbols, String).ilike(f'%"{_escape_like(normalized_symbol)}"%', escape="\\"))
    if query_text:
        term = _escape_like(query_text.strip()[:100])
        if term:
            pattern = f"%{term}%"
            query = query.filter(
                or_(
                    NormalizedDocument.title.ilike(pattern, escape="\\"),
                    NormalizedDocument.summary.ilike(pattern, escape="\\"),
                )
            )
    language_fallback = False
    if language:
        language_predicate = (
            NormalizedDocument.language.in_(("zh", "zh-CN", "zh-cn", "zh-TW"))
            if language == "zh"
            else NormalizedDocument.language == language
        )
        language_query = query.filter(language_predicate)
        # English REST data is intentionally delayed relative to Chinese RSS.
        # During warm-up or an API incident, keep the wire useful but make the
        # cross-language fallback explicit in response metadata and every item.
        if language == "en" and language_query.with_entities(NormalizedDocument.id).limit(1).first() is None:
            language_fallback = True
        else:
            query = language_query
    decoded_cursor = _decode_cursor(cursor)
    if decoded_cursor:
        cursor_at, cursor_id = decoded_cursor
        query = query.filter(
            or_(
                sort_at < cursor_at,
                and_(sort_at == cursor_at, NormalizedDocument.id < cursor_id),
            )
        )
    rows = query.order_by(sort_at.desc(), NormalizedDocument.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        last_sort_at = _utc(last.published_at) or _utc(last.created_at) or now
        next_cursor = _encode_cursor(last_sort_at, last.id)

    sources = [db.get(DataSource, provider_id) for provider_id in _providers(source)]
    last_success = max((_utc(item.last_success_at) for item in sources if item and item.last_success_at), default=None)
    source_statuses = [item.status for item in sources if item]
    status = "WARMING" if not source_statuses else "HEALTHY" if "HEALTHY" in source_statuses else source_statuses[0]
    return {
        "items": [_serialize(row, now) for row in visible],
        "page": {
            "limit": limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
        },
        "meta": {
            "status": status,
            "source": source,
            "kind": kind,
            "language": language,
            "language_fallback": language_fallback,
            "window_hours": hours,
            "last_success_at": _iso(last_success),
            "generated_at": _iso(now),
            "refresh_after_seconds": 60,
            "rss_target_latency_minutes": 5,
            "rest_documented_latency_minutes": 15,
            "research_only": True,
            "disclaimer": "Headlines and linked summaries are attributed to their publishers. Open the original source for the authoritative text.",
        },
    }
