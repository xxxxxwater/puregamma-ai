"""Trending tickers from the ingested news/social document pipeline.

Counts entity mentions across normalized documents (RSS, fintwit, X) over a
recent window. This is the system's own first-party buzz signal: no external
API key required and every count is traceable to stored source documents.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from packages.database.models import EntityMention, NormalizedDocument


def top_trending(
    db: Session,
    hours: int = 24,
    limit: int = 5,
    providers: tuple[str, ...] | None = None,
) -> list[dict]:
    """Return the most-mentioned tickers in the last `hours` hours.

    Each item: {"symbol", "mentions", "sample_title"}; empty list when the
    document pipeline has not ingested anything in the window. When
    `providers` is given, only documents from those providers are counted
    (used to gate plan-restricted sources such as X/Twitter).
    """
    if providers is not None and not providers:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 168)))
    query = (
        db.query(EntityMention.symbol, func.count(EntityMention.id).label("mentions"))
        .filter(EntityMention.created_at >= cutoff)
    )
    if providers:
        query = query.join(
            NormalizedDocument, EntityMention.document_id == NormalizedDocument.id
        ).filter(NormalizedDocument.provider.in_(providers))
    rows = (
        query.group_by(EntityMention.symbol)
        .order_by(func.count(EntityMention.id).desc(), EntityMention.symbol.asc())
        .limit(max(1, min(limit, 20)))
        .all()
    )
    trending: list[dict] = []
    for symbol, mentions in rows:
        sample_query = (
            db.query(NormalizedDocument.title)
            .join(EntityMention, EntityMention.document_id == NormalizedDocument.id)
            .filter(EntityMention.symbol == symbol, EntityMention.created_at >= cutoff)
        )
        if providers:
            sample_query = sample_query.filter(NormalizedDocument.provider.in_(providers))
        sample = sample_query.order_by(NormalizedDocument.created_at.desc()).first()
        trending.append(
            {
                "symbol": symbol,
                "mentions": int(mentions),
                "sample_title": (sample[0] if sample else "") or "",
            }
        )
    return trending
