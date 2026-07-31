from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from packages.data.sentiment import score_text


ASSET_ALIASES = {
    "BTC": ("BTC", "BITCOIN"),
    "ETH": ("ETH", "ETHEREUM", "ETHER"),
    "SOL": ("SOL", "SOLANA"),
    "HYPE": ("HYPE", "HYPERLIQUID"),
    "MSTR": ("MSTR", "MICROSTRATEGY", "STRATEGY INC"),
    "STRC": ("STRC",),
}
TOPIC_TERMS = {
    "crypto": ("crypto", "bitcoin", "ethereum", "solana", "token", "blockchain"),
    "macro": ("inflation", "fed", "rates", "yield", "gdp", "dollar", "macro"),
    "ETF": ("etf", "exchange-traded fund", "inflow", "outflow"),
    "regulation": ("regulation", "regulator", "sec", "cftc", "law", "ban"),
    "market": ("market", "price", "rally", "selloff", "volatility", "liquidity"),
    "technology": ("protocol", "upgrade", "network", "developer", "technology"),
}


def canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    query = [(key, item) for key, item in parse_qsl(parts.query) if not key.lower().startswith(("utm_", "ref"))]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def stable_hash(title: str, content: str, url: str) -> str:
    material = "\n".join((canonical_url(url), _compact(title), _compact(content)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def event_fingerprint(title: str, symbols: list[str], published_at: datetime | None) -> str:
    words = re.findall(r"[a-z0-9]{3,}", title.lower())
    day = _aware(published_at).strftime("%Y-%m-%d") if published_at else "unknown"
    material = "|".join((day, ",".join(sorted(symbols)), " ".join(sorted(set(words))[:16])))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def extract_symbols(text: str) -> list[str]:
    upper = text.upper()
    found: list[str] = []
    for symbol, aliases in ASSET_ALIASES.items():
        if any(re.search(rf"(?<![A-Z0-9])\$?{re.escape(alias)}(?![A-Z0-9])", upper) for alias in aliases):
            found.append(symbol)
    return found


def classify_topics(text: str) -> list[str]:
    lowered = text.lower()
    return [topic for topic, terms in TOPIC_TERMS.items() if any(term in lowered for term in terms)]


def summarize(text: str, limit: int = 360) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    boundary = compact.rfind(". ", 0, limit)
    return compact[: boundary + 1 if boundary > 100 else limit].rstrip()


def sentiment(text: str) -> dict[str, float | str]:
    value, label = score_text(text)
    return {"score": value, "label": label, "model": "lexicon-v1"}


def freshness_score(published_at: datetime | None, now: datetime | None = None) -> float:
    if not published_at:
        return 0.35
    age_hours = max(0.0, ((_aware(now or datetime.now(timezone.utc)) - _aware(published_at)).total_seconds() / 3600))
    return max(0.05, math.exp(-age_hours / 72.0))


def engagement_score(metrics: dict) -> float:
    weighted = (
        float(metrics.get("like_count", 0) or 0)
        + 2 * float(metrics.get("reply_count", 0) or 0)
        + 1.5 * float(metrics.get("retweet_count", metrics.get("repost_count", 0)) or 0)
        + 0.5 * float(metrics.get("quote_count", 0) or 0)
    )
    return min(1.0, 0.25 + math.log1p(max(0.0, weighted)) / 12.0)


def weighted_sentiment(sentiment_score: float, credibility: float, freshness: float, engagement: float, relevance: float) -> float:
    return max(-1.0, min(1.0, sentiment_score * credibility * freshness * engagement * relevance))


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
