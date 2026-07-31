"""Unified research fact & event impact engine (vertical slice P0-1).

Builds deduplicated, evidence-backed MarketEvents from real stored data only:

* price_move          — MarketQuoteRecord / MarketSnapshot 24h moves >= 5%
* news                — NormalizedDocument rows from the ingestion pipeline
* earnings_confirmed  — Nasdaq public earnings calendar (never estimates)
* macro_scheduled     — deterministic rule calendar (macro_calendar_rule)
* options_regime      — Deribit public context compared against the baseline
                        stored on previous research snapshots (no baseline, no
                        event — nothing is fabricated)

Every source reports per-source health on the snapshot. When a source is down
its lists stay empty and health shows the failure. No LLM calls happen here.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from packages.data import earnings_calendar, macro_calendar
from packages.data.earnings_calendar import ProviderUnavailable
from packages.database.models import (
    Alert,
    AssetImpact,
    MarketEvent,
    MarketQuoteRecord,
    MarketSnapshot,
    NormalizedDocument,
    NotificationDelivery,
    RawDocument,
    ResearchAction,
    ResearchSnapshot,
    TradingAccount,
    User,
    UserPortfolioImpact,
    UserPreference,
    utcnow,
)

logger = logging.getLogger(__name__)

PRICE_MOVE_THRESHOLD_PCT = 5.0
FRESH_DATA_MINUTES = 30
NEWS_LIMIT = 50
EARNINGS_LOOKAHEAD_DAYS = 7
MACRO_LOOKAHEAD_DAYS = 14
OPTIONS_IV_SHIFT_POINTS = 5.0
OPTIONS_GAMMA_REL_SHIFT = 0.5
SNAPSHOT_STALE_MINUTES = 60
MACRO_MAJORS = ("BTC", "ETH")
DERIBIT_CURRENCIES = ("BTC", "ETH")
ACTION_TYPES = ("ask_agent", "add_alert", "generate_report")
SCHEDULED_EVENT_TYPES = ("earnings_confirmed", "macro_scheduled")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    aware = _as_utc(value)
    return aware.isoformat() if aware else None


def _normalize_title(title: str) -> str:
    return " ".join(str(title).split()).lower()


def _fingerprint(event_type: str, title: str, source_url: str | None, publish_date: str) -> str:
    raw = f"{event_type}|{_normalize_title(title)}|{source_url or ''}|{publish_date}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _health_entry(
    status: str,
    *,
    last_success_at: datetime | None = None,
    error: str | None = None,
    items: int = 0,
    **extra: Any,
) -> dict:
    entry = {
        "status": status,
        "last_success_at": _iso(last_success_at),
        "error": error,
        "items": items,
    }
    entry.update(extra)
    return entry


# ---------------------------------------------------------------------------
# Event source builders (each returns candidate dicts and records health)
# ---------------------------------------------------------------------------


def _price_move_candidate(
    *,
    symbol: str,
    pct: float,
    observed_at: datetime,
    now: datetime,
    provider: str,
    source_url: str | None,
    evidence: list[dict],
    detail: str,
) -> dict:
    direction = "up" if pct > 0 else "down"
    title = f"{symbol} {direction} {abs(pct):.1f}% in 24h"
    age_minutes = (now - observed_at).total_seconds() / 60
    confidence = 0.9 if age_minutes < FRESH_DATA_MINUTES else 0.6
    summary = (
        f"{symbol} moved {pct:+.2f}% over the trailing 24h window, beyond the "
        f"{PRICE_MOVE_THRESHOLD_PCT:.0f}% price-move threshold. {detail}. "
        f"Observed at {observed_at.isoformat()} (UTC)."
    )
    return {
        "event_type": "price_move",
        "title": title,
        "summary": summary,
        "source_provider": provider,
        "source_url": source_url,
        "source_published_at": observed_at,
        "assets": [symbol],
        "direction": direction,
        "time_horizon": "intraday",
        "confidence": confidence,
        "evidence": evidence,
        "evidence_gaps": [],
        "fingerprint": _fingerprint("price_move", title, source_url, observed_at.date().isoformat()),
    }


def _price_move_candidates(db: Session, window_start: datetime, now: datetime, health: dict) -> list[dict]:
    source = "price_move"
    try:
        quotes = (
            db.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.fetched_at >= window_start)
            .order_by(MarketQuoteRecord.fetched_at.desc())
            .all()
        )
        snapshots = (
            db.query(MarketSnapshot)
            .filter(MarketSnapshot.timestamp >= window_start)
            .order_by(MarketSnapshot.timestamp.desc())
            .all()
        )
    except Exception as exc:
        health[source] = _health_entry("unavailable", error=str(exc)[:300])
        return []
    if not quotes and not snapshots:
        health[source] = _health_entry("degraded", error="no market data rows in window")
        return []

    candidates: list[dict] = []
    handled_assets: set[str] = set()
    latest_quote_by_asset: dict[str, MarketQuoteRecord] = {}
    for row in quotes:
        asset = str(row.base_asset or row.symbol or "").upper()
        if asset and asset not in latest_quote_by_asset:
            latest_quote_by_asset[asset] = row
    for asset, row in latest_quote_by_asset.items():
        pct = float(row.change_24h_pct) if row.change_24h_pct is not None else None
        if pct is None or abs(pct) < PRICE_MOVE_THRESHOLD_PCT:
            continue
        handled_assets.add(asset)
        observed_at = _as_utc(row.source_timestamp) or _as_utc(row.fetched_at) or now
        source_url = str((row.provenance_json or {}).get("source_url") or "") or None
        evidence = [
            {
                "kind": "market_quote",
                "ref": row.id,
                "url": source_url,
                "published_at": observed_at.isoformat(),
                "change_24h_pct": round(pct, 4),
            }
        ]
        candidates.append(
            _price_move_candidate(
                symbol=asset,
                pct=pct,
                observed_at=observed_at,
                now=now,
                provider=f"market_quotes:{row.provider}",
                source_url=source_url,
                evidence=evidence,
                detail=f"Stored 24h change {pct:+.2f}% from provider {row.provider}",
            )
        )

    # MarketSnapshot fallback: derive the move from the latest two stored
    # snapshots per asset when no stored 24h change exists.
    snapshots_by_asset: dict[str, list[MarketSnapshot]] = {}
    for row in snapshots:
        asset = str(row.asset_id or "").upper()
        if not asset or asset in handled_assets:
            continue
        bucket = snapshots_by_asset.setdefault(asset, [])
        if len(bucket) < 2:
            bucket.append(row)
    for asset, rows in snapshots_by_asset.items():
        if len(rows) < 2:
            continue
        latest, previous = rows[0], rows[1]
        if not previous.price:
            continue
        pct = (float(latest.price) - float(previous.price)) / float(previous.price) * 100.0
        if abs(pct) < PRICE_MOVE_THRESHOLD_PCT:
            continue
        observed_at = _as_utc(latest.timestamp) or now
        evidence = [
            {
                "kind": "market_snapshot",
                "ref": row.id,
                "url": None,
                "published_at": (_as_utc(row.timestamp) or now).isoformat(),
                **({"change_24h_pct": round(pct, 4)} if row is latest else {}),
            }
            for row in (latest, previous)
        ]
        candidates.append(
            _price_move_candidate(
                symbol=asset,
                pct=pct,
                observed_at=observed_at,
                now=now,
                provider="market_snapshots",
                source_url=None,
                evidence=evidence,
                detail=(
                    f"Computed {pct:+.2f}% from stored snapshots "
                    f"{float(previous.price):.8g} -> {float(latest.price):.8g}"
                ),
            )
        )
    health[source] = _health_entry("ok", last_success_at=now, items=len(candidates))
    return candidates


def _news_candidates(db: Session, window_start: datetime, now: datetime, health: dict) -> list[dict]:
    source = "news"
    try:
        docs = (
            db.query(NormalizedDocument)
            .filter(NormalizedDocument.created_at >= window_start)
            .order_by(NormalizedDocument.final_score.desc())
            .limit(NEWS_LIMIT)
            .all()
        )
    except Exception as exc:
        health[source] = _health_entry("unavailable", error=str(exc)[:300])
        return []
    if not docs:
        health[source] = _health_entry("degraded", error="no normalized documents in window")
        return []

    candidates: list[dict] = []
    for doc in docs:
        raw = db.get(RawDocument, doc.raw_document_id)
        payload = (raw.raw_payload or {}) if raw else {}
        source_url = (
            payload.get("url")
            or payload.get("link")
            or (raw.source_url if raw else None)
            or doc.url
        )
        published = _as_utc(doc.published_at) or _as_utc(doc.created_at) or now
        title = " ".join(str(doc.title or "").split())[:200] or f"News document {doc.id}"
        symbols = sorted({str(item).upper() for item in (doc.symbols or []) if str(item).strip()})
        confidence = min(0.95, float(doc.final_score or 0.5))
        summary = str(doc.summary or doc.content or "")[:400]
        evidence = [
            {
                "kind": "news_document",
                "ref": doc.id,
                "url": source_url,
                "published_at": published.isoformat(),
            }
        ]
        candidates.append(
            {
                "event_type": "news",
                "title": title,
                "summary": summary,
                "source_provider": f"news:{doc.provider}",
                "source_url": source_url,
                "source_published_at": published,
                "assets": symbols,
                "direction": None,
                "time_horizon": "intraday",
                "confidence": confidence,
                "evidence": evidence,
                "evidence_gaps": [] if source_url else ["source_url_missing"],
                "fingerprint": _fingerprint("news", title, source_url, published.date().isoformat()),
            }
        )
    health[source] = _health_entry("ok", last_success_at=now, items=len(candidates))
    return candidates


def _earnings_candidates(now: datetime, health: dict) -> list[dict]:
    source = "earnings_confirmed"
    try:
        rows = earnings_calendar.upcoming_confirmed_earnings(now.date(), days=EARNINGS_LOOKAHEAD_DAYS)
    except ProviderUnavailable as exc:
        health[source] = _health_entry("unavailable", error=str(exc)[:300])
        return []
    except Exception as exc:
        health[source] = _health_entry("unavailable", error=str(exc)[:300])
        return []

    candidates: list[dict] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        as_of = str(row.get("as_of") or "")
        if not symbol or not as_of:
            continue
        try:
            report_day = date.fromisoformat(as_of)
        except ValueError:
            continue
        scheduled_at = datetime.combine(report_day, time.min, tzinfo=timezone.utc)
        time_label = row.get("time_label") or "time not supplied"
        title = f"{symbol} earnings confirmed for {as_of}"
        summary = (
            f"{row.get('name') or symbol} ({symbol}) reports earnings on {as_of} ({time_label}). "
            "Confirmed via the Nasdaq earnings calendar."
        )
        if row.get("eps_forecast"):
            summary += f" EPS forecast: {row['eps_forecast']}."
        if row.get("market_cap"):
            summary += f" Market cap: {row['market_cap']}."
        source_url = row.get("source_url") or earnings_calendar.NASDAQ_EARNINGS_PAGE_URL
        evidence = [
            {
                "kind": "earnings_calendar",
                "ref": f"nasdaq:{symbol}:{as_of}",
                "url": source_url,
                "published_at": scheduled_at.isoformat(),
            }
        ]
        candidates.append(
            {
                "event_type": "earnings_confirmed",
                "title": title,
                "summary": summary,
                "source_provider": "nasdaq_earnings_calendar",
                "source_url": source_url,
                "source_published_at": scheduled_at,
                "assets": [symbol],
                "direction": None,
                "time_horizon": "days",
                "confidence": 0.95,
                "evidence": evidence,
                "evidence_gaps": [],
                "fingerprint": _fingerprint("earnings_confirmed", title, source_url, as_of),
            }
        )
    health[source] = _health_entry("ok", last_success_at=now, items=len(candidates))
    return candidates


def _macro_candidates(now: datetime, health: dict) -> list[dict]:
    source = "macro_scheduled"
    today = now.date()
    candidates: list[dict] = []
    for offset in range(MACRO_LOOKAHEAD_DAYS):
        day = today + timedelta(days=offset)
        for label in macro_calendar.events_for(day, "en"):
            scheduled_at = datetime.combine(day, time.min, tzinfo=timezone.utc)
            title = f"{label} — {day.isoformat()}"
            summary = (
                f"{label} is scheduled for {day.isoformat()}. Dates come from the built-in "
                "rule-based macro calendar (macro_calendar_rule): deterministic rule-based "
                "scheduling, not a confirmed provider timestamp."
            )
            evidence = [
                {
                    "kind": "macro_calendar_rule",
                    "ref": f"macro:{label}:{day.isoformat()}",
                    "url": None,
                    "published_at": scheduled_at.isoformat(),
                }
            ]
            candidates.append(
                {
                    "event_type": "macro_scheduled",
                    "title": title,
                    "summary": summary,
                    "source_provider": "macro_calendar_rule",
                    "source_url": None,
                    "source_published_at": scheduled_at,
                    "assets": [],
                    "direction": None,
                    "time_horizon": "days",
                    "confidence": 1.0,
                    "evidence": evidence,
                    "evidence_gaps": ["rule_based_schedule_not_provider_confirmed"],
                    "fingerprint": _fingerprint("macro_scheduled", title, None, day.isoformat()),
                }
            )
    health[source] = _health_entry("ok", last_success_at=now, items=len(candidates))
    return candidates


def _fetch_deribit_metrics() -> dict[str, dict] | None:
    """Read-only Deribit public context for regime detection.

    Returns {currency: {atm_iv, gamma_exposure, instrument_count, as_of}} or
    None when no usable Deribit context exists. Never fabricates values.
    """
    try:
        from apps.api.services import options_service
    except Exception:
        return None
    metrics: dict[str, dict] = {}
    for currency in DERIBIT_CURRENCIES:
        try:
            chain = options_service.get_option_chain(currency)
        except Exception:
            continue
        if not isinstance(chain, dict) or chain.get("status") != "HEALTHY":
            continue
        instruments = chain.get("instruments") or []
        if not instruments:
            continue
        underlying = next(
            (float(item["underlying_price"]) for item in instruments if item.get("underlying_price")),
            None,
        )
        atm_iv = None
        if underlying:
            atm_candidates = [
                item
                for item in instruments
                if item.get("mark_iv") is not None and item.get("strike") is not None
            ]
            if atm_candidates:
                best = min(atm_candidates, key=lambda item: abs(float(item["strike"]) - underlying))
                atm_iv = float(best["mark_iv"])
        gamma_exposure = 0.0
        for item in instruments:
            greeks = item.get("greeks") or {}
            gamma = greeks.get("gamma")
            open_interest = item.get("open_interest")
            if gamma is None or open_interest is None:
                continue
            gamma_exposure += float(gamma) * float(open_interest)
        metrics[currency] = {
            "atm_iv": atm_iv,
            "gamma_exposure": gamma_exposure,
            "instrument_count": len(instruments),
            "as_of": chain.get("fetched_at"),
        }
    return metrics or None


def _options_regime_candidates(db: Session, snapshot: ResearchSnapshot, now: datetime, health: dict) -> list[dict]:
    source = "options_regime"
    metrics = _fetch_deribit_metrics()
    if not metrics:
        health[source] = _health_entry("unavailable", error="deribit public context unavailable")
        return []
    entry = _health_entry("ok", last_success_at=now, items=0)
    entry["metrics"] = metrics
    health[source] = entry

    previous = (
        db.query(ResearchSnapshot)
        .filter(ResearchSnapshot.id != snapshot.id, ResearchSnapshot.status == "completed")
        .order_by(ResearchSnapshot.as_of.desc())
        .first()
    )
    previous_metrics = None
    if previous and isinstance(previous.health_json, dict):
        previous_metrics = (previous.health_json.get(source) or {}).get("metrics") or None
    if not previous_metrics:
        # No stored baseline: record today's baseline only, emit nothing.
        entry["note"] = "baseline_recorded"
        return []

    candidates: list[dict] = []
    for currency, current in metrics.items():
        previous = previous_metrics.get(currency)
        if not previous:
            continue
        atm_now = current.get("atm_iv")
        atm_prev = previous.get("atm_iv")
        gamma_now = current.get("gamma_exposure")
        gamma_prev = previous.get("gamma_exposure")
        iv_shift = abs(atm_now - atm_prev) if atm_now is not None and atm_prev is not None else 0.0
        gamma_flip = (
            gamma_now is not None
            and gamma_prev is not None
            and gamma_now != 0
            and gamma_prev != 0
            and (gamma_now > 0) != (gamma_prev > 0)
        )
        gamma_rel = (
            abs(gamma_now - gamma_prev) / max(abs(gamma_prev), 1e-9)
            if gamma_now is not None and gamma_prev is not None
            else 0.0
        )
        if iv_shift < OPTIONS_IV_SHIFT_POINTS and not gamma_flip and gamma_rel < OPTIONS_GAMMA_REL_SHIFT:
            continue
        title = f"{currency} options regime shift: ATM IV {atm_prev} -> {atm_now}"
        summary = (
            f"{currency} Deribit options context moved beyond regime thresholds versus the stored "
            f"baseline: ATM IV {atm_prev} -> {atm_now} (shift {iv_shift:.2f} vol points, threshold "
            f"{OPTIONS_IV_SHIFT_POINTS:.0f}), gamma exposure {gamma_prev} -> {gamma_now} "
            f"(relative shift {gamma_rel:.2f}, threshold {OPTIONS_GAMMA_REL_SHIFT:.2f}, sign flip: "
            f"{'yes' if gamma_flip else 'no'}). Baseline read from the previous research snapshot; "
            "source is the Deribit public API."
        )
        publish_date = now.date().isoformat()
        source_url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
        evidence = [
            {
                "kind": "options_context",
                "ref": f"deribit:{currency}:{publish_date}",
                "url": source_url,
                "published_at": now.isoformat(),
            }
        ]
        candidates.append(
            {
                "event_type": "options_regime",
                "title": title,
                "summary": summary,
                "source_provider": "deribit_public",
                "source_url": source_url,
                "source_published_at": now,
                "assets": [currency],
                "direction": None,
                "time_horizon": "days",
                "confidence": 0.7,
                "evidence": evidence,
                "evidence_gaps": [],
                "fingerprint": _fingerprint("options_regime", title, source_url, publish_date),
            }
        )
    entry["items"] = len(candidates)
    return candidates


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def _persist_candidates(
    db: Session,
    snapshot: ResearchSnapshot,
    candidates: list[dict],
    existing_fingerprints: set[str],
    now: datetime,
) -> list[MarketEvent]:
    created: list[MarketEvent] = []
    for candidate in candidates:
        fingerprint = candidate["fingerprint"]
        if fingerprint in existing_fingerprints:
            continue
        event = MarketEvent(
            event_type=candidate["event_type"],
            title=candidate["title"],
            summary=candidate["summary"],
            source_provider=candidate["source_provider"],
            source_url=candidate.get("source_url"),
            source_published_at=candidate.get("source_published_at"),
            collected_at=now,
            data_cutoff_at=now,
            fingerprint=fingerprint,
            assets=candidate.get("assets") or [],
            direction=candidate.get("direction"),
            time_horizon=candidate.get("time_horizon"),
            confidence=float(candidate.get("confidence") or 0.0),
            evidence_json=candidate.get("evidence") or [],
            evidence_gaps=candidate.get("evidence_gaps") or [],
            research_snapshot_id=snapshot.id,
            status="active",
        )
        db.add(event)
        existing_fingerprints.add(fingerprint)
        created.append(event)
    db.flush()
    return created


def build_research_events(db: Session, kind: str = "intraday", window_hours: int = 24) -> ResearchSnapshot:
    """Idempotent research build: one snapshot plus deduplicated events.

    Re-runs never duplicate events; dedup is by sha256 fingerprint of
    (event_type, normalized title, source url, publish date).
    """
    now = utcnow()
    window_start = now - timedelta(hours=window_hours)
    snapshot = ResearchSnapshot(
        kind=kind,
        as_of=now,
        data_cutoff_at=now,
        window_start=window_start,
        window_end=now,
        status="building",
    )
    db.add(snapshot)
    db.flush()

    health: dict[str, dict] = {}
    existing_fingerprints = {row[0] for row in db.query(MarketEvent.fingerprint).all()}

    candidates: list[dict] = []
    candidates.extend(_price_move_candidates(db, window_start, now, health))
    candidates.extend(_news_candidates(db, window_start, now, health))
    candidates.extend(_earnings_candidates(now, health))
    candidates.extend(_macro_candidates(now, health))
    candidates.extend(_options_regime_candidates(db, snapshot, now, health))

    created = _persist_candidates(db, snapshot, candidates, existing_fingerprints, now)
    source_counts: dict[str, int] = {}
    for event in created:
        source_counts[event.event_type] = source_counts.get(event.event_type, 0) + 1

    snapshot.source_counts_json = source_counts
    snapshot.health_json = health
    snapshot.status = "completed"
    db.commit()
    return snapshot


# ---------------------------------------------------------------------------
# Impact computation
# ---------------------------------------------------------------------------


def _event_magnitude(event: MarketEvent) -> float | None:
    for entry in event.evidence_json or []:
        if isinstance(entry, dict) and entry.get("change_24h_pct") is not None:
            try:
                return float(entry["change_24h_pct"])
            except (TypeError, ValueError):
                return None
    return None


def _direct_rationale(event: MarketEvent) -> str:
    if event.event_type == "price_move":
        return (
            "Direct observation: the asset's own 24h price move exceeded the "
            f"{PRICE_MOVE_THRESHOLD_PCT:.0f}% threshold in stored market data."
        )
    if event.event_type == "news":
        return "Direct mention: the asset is listed in the normalized document's symbols."
    if event.event_type == "earnings_confirmed":
        return "Direct: the company's own confirmed earnings date (Nasdaq calendar)."
    if event.event_type == "options_regime":
        return "Direct: the underlying's own Deribit options context shifted versus the stored baseline."
    return "Direct relation recorded by the research pipeline."


def compute_asset_impacts(db: Session, snapshot: ResearchSnapshot) -> dict:
    """Create AssetImpact rows for the snapshot's events (rerun-safe).

    relation_type="statistical" is reserved for explicit price co-move
    evidence; this slice computes no correlations, so no statistical impacts
    are ever fabricated here.
    """
    events = db.query(MarketEvent).filter(MarketEvent.research_snapshot_id == snapshot.id).all()
    if not events:
        return {"events": 0, "created": 0}
    event_ids = [event.id for event in events]
    existing = {
        (row[0], row[1], row[2])
        for row in db.query(AssetImpact.event_id, AssetImpact.symbol, AssetImpact.relation_type)
        .filter(AssetImpact.event_id.in_(event_ids))
        .all()
    }
    created = 0
    for event in events:
        magnitude = _event_magnitude(event)
        for symbol in event.assets or []:
            sym = str(symbol).upper()
            key = (event.id, sym, "direct")
            if key in existing:
                continue
            db.add(
                AssetImpact(
                    event_id=event.id,
                    symbol=sym,
                    relation_type="direct",
                    direction=event.direction,
                    magnitude=magnitude,
                    confidence=event.confidence,
                    horizon=event.time_horizon,
                    rationale=_direct_rationale(event),
                )
            )
            existing.add(key)
            created += 1
        if event.event_type == "macro_scheduled":
            for sym in MACRO_MAJORS:
                key = (event.id, sym, "macro")
                if key in existing:
                    continue
                db.add(
                    AssetImpact(
                        event_id=event.id,
                        symbol=sym,
                        relation_type="macro",
                        direction="unknown",
                        magnitude=None,
                        confidence=event.confidence,
                        horizon=event.time_horizon,
                        rationale=(
                            "BTC/ETH are macro-sensitive majors linked to scheduled macro releases. "
                            "Rule-based scheduling linkage only; not evidence of causation."
                        ),
                    )
                )
                existing.add(key)
                created += 1
    db.commit()
    return {"events": len(events), "created": created}


def _action_title(action_type: str, event: MarketEvent) -> str:
    if action_type == "ask_agent":
        return f"Ask agent about: {event.title}"
    if action_type == "add_alert":
        return f"Add alert for: {event.title}"
    return f"Generate report on: {event.title}"


def _action_payload(action_type: str, event: MarketEvent, user_id: str | None, symbols: list[str]) -> dict:
    assets_text = ", ".join(symbols) if symbols else "the affected assets"
    scope = f"my holdings in {assets_text}" if user_id else f"portfolios exposed to {assets_text}"
    if action_type == "ask_agent":
        prompt = (
            f"Research event: {event.title}\n\n{event.summary}\n\n"
            f"Explain what changed, walk through the stored evidence and provenance, and assess "
            f"the potential impact on {scope}. Cite only the stored evidence; do not invent data."
        )
    elif action_type == "add_alert":
        prompt = (
            f"Create an alert tied to research event '{event.title}' (event_id={event.id}) for "
            f"{assets_text}. Use the stored event provenance as the alert context."
        )
    else:
        prompt = (
            f"Generate a research report on event '{event.title}' (event_id={event.id}) using the "
            f"stored evidence, asset impacts and portfolio exposures. Do not invent facts."
        )
    return {
        "prompt": prompt,
        "event_id": event.id,
        "event_type": event.event_type,
        "symbols": symbols,
        "source_url": event.source_url,
        "locale": "en",
    }


def _create_research_actions(
    db: Session,
    events: list[MarketEvent],
    impacted_users_by_event: dict[str, dict[str, list[str]]],
    now: datetime,
) -> int:
    ranked = sorted(
        events,
        key=lambda event: (event.confidence, _as_utc(event.created_at) or now),
        reverse=True,
    )[:3]
    existing_keys = {row[0] for row in db.query(ResearchAction.dedup_key).all()}
    created = 0
    for event in ranked:
        impacted = impacted_users_by_event.get(event.id) or {}
        for action_type in ACTION_TYPES:
            targets: list[tuple[str | None, list[str]]] = [
                (user_id, symbols) for user_id, symbols in sorted(impacted.items())
            ]
            if not targets:
                targets = [(None, [str(item).upper() for item in (event.assets or [])])]
            for user_id, symbols in targets:
                dedup_key = f"{action_type}:{user_id or 'global'}:{event.id}"
                if dedup_key in existing_keys:
                    continue
                db.add(
                    ResearchAction(
                        user_id=user_id,
                        event_id=event.id,
                        action_type=action_type,
                        title=_action_title(action_type, event),
                        payload_json=_action_payload(action_type, event, user_id, symbols),
                        status="open",
                        dedup_key=dedup_key,
                    )
                )
                existing_keys.add(dedup_key)
                created += 1
    return created


def compute_user_portfolio_impacts(db: Session, snapshot: ResearchSnapshot) -> dict:
    """Map the snapshot's asset impacts onto real user holdings (rerun-safe).

    Holdings come from the same source as the /portfolio snapshot view
    (AccountSnapshot + PositionSnapshot aggregation in portfolio_service).
    Users without holdings are skipped.
    """
    # Lazy import keeps the module import graph light for workers/tests.
    from apps.api.services.portfolio_service import portfolio_view

    events = db.query(MarketEvent).filter(MarketEvent.research_snapshot_id == snapshot.id).all()
    if not events:
        return {"users": 0, "created": 0, "actions": 0}
    event_ids = [event.id for event in events]
    impacts_by_event: dict[str, list[AssetImpact]] = {event_id: [] for event_id in event_ids}
    for impact in db.query(AssetImpact).filter(AssetImpact.event_id.in_(event_ids)).all():
        impacts_by_event.setdefault(impact.event_id, []).append(impact)
    existing_pairs = {
        (row[0], row[1], row[2])
        for row in db.query(UserPortfolioImpact.user_id, UserPortfolioImpact.event_id, UserPortfolioImpact.symbol)
        .filter(UserPortfolioImpact.event_id.in_(event_ids))
        .all()
    }
    user_ids = [
        row[0]
        for row in db.query(TradingAccount.user_id)
        .filter(TradingAccount.account_type == "READ_ONLY", TradingAccount.status == "ACTIVE")
        .distinct()
        .all()
    ]
    now = utcnow()
    created = 0
    for user_id in user_ids:
        user = db.get(User, user_id)
        if not user:
            continue
        try:
            view = portfolio_view(db, user)
        except Exception:
            db.rollback()
            logger.warning("research_portfolio_view_failed user_id=%s", user_id, exc_info=True)
            continue
        holdings = view.get("holdings") or []
        nav = float(view.get("nav") or 0.0)
        if not holdings:
            continue
        by_symbol = {
            str(item.get("symbol") or "").upper(): item for item in holdings if item.get("symbol")
        }
        for event in events:
            for impact in impacts_by_event.get(event.id, []):
                holding = by_symbol.get(str(impact.symbol).upper())
                if not holding:
                    continue
                key = (user_id, event.id, impact.symbol)
                if key in existing_pairs:
                    continue
                value = float(holding.get("value") or 0.0)
                db.add(
                    UserPortfolioImpact(
                        user_id=user_id,
                        event_id=event.id,
                        asset_impact_id=impact.id,
                        symbol=impact.symbol,
                        exposure_value=value,
                        exposure_weight=(value / nav) if nav > 0 else None,
                        direction=impact.direction,
                        confidence=impact.confidence,
                        computed_at=now,
                    )
                )
                existing_pairs.add(key)
                created += 1
    # Action targeting uses the full stored impact set (not only rows created
    # in this run) so reruns stay idempotent.
    db.flush()
    impacted_users_by_event: dict[str, dict[str, list[str]]] = {}
    for row in (
        db.query(UserPortfolioImpact.event_id, UserPortfolioImpact.user_id, UserPortfolioImpact.symbol)
        .filter(UserPortfolioImpact.event_id.in_(event_ids))
        .all()
    ):
        symbols = impacted_users_by_event.setdefault(row[0], {}).setdefault(row[1], [])
        if row[2] not in symbols:
            symbols.append(row[2])
    actions_created = _create_research_actions(db, events, impacted_users_by_event, now)
    db.commit()
    return {"users": len(user_ids), "created": created, "actions": actions_created}


# ---------------------------------------------------------------------------
# Event alerts (exactly-once fan-out from events to user channels)
# ---------------------------------------------------------------------------


def _alert_severity(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _event_alert_targets(db: Session, event: MarketEvent) -> dict[str, list[str]]:
    """Users with a stored UserPortfolioImpact for this event, with symbols.

    Real holdings linkage only: users without a stored impact row for the
    event are never alerted.
    """
    rows = (
        db.query(UserPortfolioImpact.user_id, UserPortfolioImpact.symbol)
        .filter(UserPortfolioImpact.event_id == event.id)
        .all()
    )
    targets: dict[str, list[str]] = {}
    for user_id, symbol in rows:
        symbols = targets.setdefault(user_id, [])
        if symbol not in symbols:
            symbols.append(symbol)
    return targets


def create_alert_for_event(
    db: Session,
    event: MarketEvent,
    *,
    user_id: str | None = None,
    channels: list[str] | None = None,
    locale: str = "en",
) -> dict:
    """Minimal event -> alert fan-out, exactly-once per (user, event, channel).

    * One ``Alert`` row per (user, event): idempotency key
      ``event-alert:{user}:{event}``.
    * One ``NotificationDelivery`` per selected channel: idempotency key
      ``event-alert:{user}:{event}:{channel}``; the notification dispatcher is
      exactly-once on that key, so a rerun creates zero new rows.

    Targets: an explicit ``user_id``, or every user with a stored
    UserPortfolioImpact for the event. Channels: explicit ``channels``, or the
    user's configured notification channels; non-web channels are intersected
    with the plan's entitled channels (``web`` is the in-app inbox and is
    always allowed, mirroring the daily orchestrator).
    """
    from apps.api.services.entitlement_service import get_user_entitlement
    from apps.api.services.notification_service import send_notification

    if user_id is not None:
        targets = {user_id: [str(asset).upper() for asset in (event.assets or [])]}
    else:
        targets = _event_alert_targets(db, event)
    alerts_created = 0
    deliveries_created = 0
    users_alerted = 0
    for target_user_id, symbols in sorted(targets.items()):
        user = db.get(User, target_user_id)
        if not user:
            continue
        entitled = set(get_user_entitlement(db, target_user_id)["notification_channels"])
        if channels is None:
            preference = db.get(UserPreference, target_user_id)
            configured = [
                str(channel).lower()
                for channel in ((preference.notification_channels if preference else None) or ["email"])
                if channel
            ]
        else:
            configured = [str(channel).lower() for channel in channels if channel]
        selected = [
            channel
            for channel in dict.fromkeys(configured)
            if channel == "web" or channel in entitled
        ]
        if not selected:
            continue
        asset = symbols[0] if symbols else (str(event.assets[0]).upper() if event.assets else "MARKET")
        message = f"{event.title}\n\n{event.summary}".strip()[:1000]
        alert_key = f"event-alert:{target_user_id}:{event.id}"
        alert = db.query(Alert).filter(Alert.idempotency_key == alert_key).one_or_none()
        if alert is None:
            alert = Alert(
                user_id=target_user_id,
                asset=asset,
                message=message,
                severity=_alert_severity(float(event.confidence or 0.0)),
                channel=selected[0],
                status="pending",
                idempotency_key=alert_key,
            )
            db.add(alert)
            db.flush()
            alerts_created += 1
        sent_any = False
        for channel in selected:
            delivery_key = f"event-alert:{target_user_id}:{event.id}:{channel}"
            existed = (
                db.query(NotificationDelivery.id)
                .filter(NotificationDelivery.idempotency_key == delivery_key)
                .first()
                is not None
            )
            delivery = send_notification(
                db,
                target_user_id,
                channel,
                message,
                {
                    "idempotency_key": delivery_key,
                    "locale": locale,
                    "automation_key": "event_alert",
                },
            )
            if not existed:
                deliveries_created += 1
            sent_any = sent_any or delivery.status == "sent"
        if sent_any and alert.status != "sent":
            alert.status = "sent"
            alert.sent_at = utcnow()
        users_alerted += 1
    db.commit()
    return {"users": users_alerted, "alerts": alerts_created, "deliveries": deliveries_created}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_event(event: MarketEvent, impacts: list[AssetImpact] | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    collected_at = _as_utc(event.collected_at)
    freshness_minutes = round((now - collected_at).total_seconds() / 60, 1) if collected_at else None
    return {
        "id": event.id,
        "event_type": event.event_type,
        "title": event.title,
        "summary": event.summary,
        "source": {
            "provider": event.source_provider,
            "url": event.source_url,
            "published_at": _iso(event.source_published_at),
        },
        "collected_at": _iso(event.collected_at),
        "data_cutoff_at": _iso(event.data_cutoff_at),
        "freshness_minutes": freshness_minutes,
        "assets": list(event.assets or []),
        "impacts": [
            {
                "symbol": impact.symbol,
                "relation_type": impact.relation_type,
                "direction": impact.direction,
                "confidence": impact.confidence,
            }
            for impact in (impacts or [])
        ],
        "direction": event.direction,
        "time_horizon": event.time_horizon,
        "confidence": event.confidence,
        "evidence": list(event.evidence_json or []),
        "evidence_gaps": list(event.evidence_gaps or []),
        "status": event.status,
    }


def _impacts_by_event(db: Session, event_ids: list[str]) -> dict[str, list[AssetImpact]]:
    if not event_ids:
        return {}
    grouped: dict[str, list[AssetImpact]] = {}
    for impact in db.query(AssetImpact).filter(AssetImpact.event_id.in_(event_ids)).all():
        grouped.setdefault(impact.event_id, []).append(impact)
    return grouped


def _latest_completed_snapshot(db: Session) -> ResearchSnapshot | None:
    return (
        db.query(ResearchSnapshot)
        .filter(ResearchSnapshot.status == "completed")
        .order_by(ResearchSnapshot.as_of.desc())
        .first()
    )


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _health_payload(snapshot: ResearchSnapshot | None, now: datetime) -> dict:
    if not snapshot:
        return {
            "overall": "degraded",
            "sources": {},
            "snapshot_as_of": None,
            "snapshot_age_minutes": None,
            "note": "no_research_snapshot",
        }
    sources: dict[str, dict] = {}
    degraded = False
    for name, info in (snapshot.health_json or {}).items():
        info = info if isinstance(info, dict) else {}
        status = str(info.get("status") or "unknown")
        if status != "ok":
            degraded = True
        last_success = _parse_iso(info.get("last_success_at"))
        sources[name] = {
            "status": status,
            "last_success_at": info.get("last_success_at"),
            "error": info.get("error"),
            "items": info.get("items", 0),
            "freshness_minutes": round((now - last_success).total_seconds() / 60, 1) if last_success else None,
        }
    as_of = _as_utc(snapshot.as_of)
    age_minutes = round((now - as_of).total_seconds() / 60, 1) if as_of else None
    if age_minutes is None or age_minutes > SNAPSHOT_STALE_MINUTES:
        degraded = True
    return {
        "overall": "degraded" if degraded else "ok",
        "sources": sources,
        "snapshot_as_of": _iso(snapshot.as_of),
        "snapshot_age_minutes": age_minutes,
        "note": None,
    }


def _user_impacts_payload(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    rows = (
        db.query(UserPortfolioImpact, MarketEvent)
        .join(MarketEvent, MarketEvent.id == UserPortfolioImpact.event_id)
        .filter(UserPortfolioImpact.user_id == user_id)
        .order_by(UserPortfolioImpact.computed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": impact.id,
            "event_id": impact.event_id,
            "symbol": impact.symbol,
            "exposure_value": impact.exposure_value,
            "exposure_weight": impact.exposure_weight,
            "direction": impact.direction,
            "confidence": impact.confidence,
            "computed_at": _iso(impact.computed_at),
            "event_title": event.title,
            "event_type": event.event_type,
            "event_direction": event.direction,
        }
        for impact, event in rows
    ]


def _actions_payload(db: Session, user_id: str, limit: int = 3) -> list[dict]:
    rows = (
        db.query(ResearchAction)
        .filter(
            or_(ResearchAction.user_id == user_id, ResearchAction.user_id.is_(None)),
            ResearchAction.status == "open",
        )
        .order_by(ResearchAction.created_at.desc())
        .limit(50)
        .all()
    )
    own = [row for row in rows if row.user_id == user_id]
    shared = [row for row in rows if row.user_id is None]
    ordered = (own + shared)[:limit]
    return [
        {
            "id": row.id,
            "action_type": row.action_type,
            "title": row.title,
            "payload": dict(row.payload_json or {}),
            "status": row.status,
            "event_id": row.event_id,
            "user_scope": "user" if row.user_id else "global",
            "created_at": _iso(row.created_at),
        }
        for row in ordered
    ]


def _next_event_payload(db: Session, now: datetime) -> dict | None:
    event = (
        db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type.in_(SCHEDULED_EVENT_TYPES),
            MarketEvent.source_published_at.isnot(None),
            MarketEvent.source_published_at >= now - timedelta(hours=1),
        )
        .order_by(MarketEvent.source_published_at.asc())
        .first()
    )
    if not event:
        return None
    return {
        "id": event.id,
        "event_type": event.event_type,
        "title": event.title,
        "scheduled_at": _iso(event.source_published_at),
        "assets": list(event.assets or []),
        "source": {"provider": event.source_provider, "url": event.source_url},
    }


# ---------------------------------------------------------------------------
# Read models (router-facing)
# ---------------------------------------------------------------------------


def get_today(db: Session, user: User, locale: str = "en") -> dict:
    """The three daily answers: what happened, what it means for me, what next."""
    now = utcnow()
    snapshot = _latest_completed_snapshot(db)
    events = (
        db.query(MarketEvent)
        .filter(MarketEvent.status == "active")
        .order_by(MarketEvent.confidence.desc(), MarketEvent.created_at.desc())
        .limit(5)
        .all()
    )
    impacts = _impacts_by_event(db, [event.id for event in events])
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "overnight_events": [
            serialize_event(event, impacts.get(event.id, []), now) for event in events
        ],
        "portfolio_impacts": _user_impacts_payload(db, user.id),
        "actions": _actions_payload(db, user.id),
        "next_event": _next_event_payload(db, now),
        "health": _health_payload(snapshot, now),
        "locale": locale,
    }


def get_overnight(db: Session, user: User, since_hours: int = 14) -> dict:
    now = utcnow()
    since = now - timedelta(hours=max(1, since_hours))
    events = (
        db.query(MarketEvent)
        .filter(MarketEvent.status == "active", MarketEvent.created_at >= since)
        .order_by(MarketEvent.created_at.desc())
        .limit(20)
        .all()
    )
    impacts = _impacts_by_event(db, [event.id for event in events])
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "since_hours": since_hours,
        "events": [serialize_event(event, impacts.get(event.id, []), now) for event in events],
        "health": _health_payload(_latest_completed_snapshot(db), now),
    }


def get_portfolio_impact(db: Session, user: User) -> dict:
    now = utcnow()
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "impacts": _user_impacts_payload(db, user.id, limit=50),
        "health": _health_payload(_latest_completed_snapshot(db), now),
    }


def get_upcoming_events(db: Session, days: int = 14) -> dict:
    now = utcnow()
    horizon = now + timedelta(days=max(1, days))
    events = (
        db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type.in_(SCHEDULED_EVENT_TYPES),
            MarketEvent.source_published_at.isnot(None),
            MarketEvent.source_published_at >= now - timedelta(hours=1),
            MarketEvent.source_published_at <= horizon,
        )
        .order_by(MarketEvent.source_published_at.asc())
        .limit(100)
        .all()
    )
    impacts = _impacts_by_event(db, [event.id for event in events])
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "days": days,
        "events": [serialize_event(event, impacts.get(event.id, []), now) for event in events],
        "health": _health_payload(_latest_completed_snapshot(db), now),
    }


def get_opportunities(db: Session, user: User, locale: str = "en") -> dict:
    """Real opportunities: Deribit long-gamma + confirmed earnings + price moves."""
    now = utcnow()
    health: dict[str, dict] = {}
    long_gamma: list[dict] = []
    try:
        from apps.api.services import options_service
        from packages.options.long_gamma import discover_long_gamma

        for currency in DERIBIT_CURRENCIES:
            key = f"deribit_{currency.lower()}"
            try:
                chain = options_service.get_option_chain(currency)
            except Exception as exc:
                health[key] = {"status": "unavailable", "error": str(exc)[:200]}
                continue
            if not isinstance(chain, dict) or chain.get("status") != "HEALTHY":
                health[key] = {
                    "status": "degraded",
                    "error": (chain.get("error") if isinstance(chain, dict) else None) or "chain not healthy",
                }
                continue
            for item in discover_long_gamma(chain.get("instruments") or [], limit=5):
                long_gamma.append(
                    {
                        "currency": currency,
                        "instrument": item.get("instrument"),
                        "option_type": item.get("option_type"),
                        "strike": item.get("strike"),
                        "expiry": item.get("expiry"),
                        "days_to_expiry": item.get("days_to_expiry"),
                        "mark_iv": item.get("mark_iv"),
                        "research_score": item.get("research_score"),
                        "rationale": item.get("rationale"),
                        "source_url": chain.get("source_url"),
                        "execution_enabled": False,
                    }
                )
            health[key] = {"status": "ok", "error": None}
    except Exception as exc:
        health["deribit"] = {"status": "unavailable", "error": str(exc)[:200]}
    long_gamma.sort(key=lambda item: item.get("research_score") or 0, reverse=True)
    long_gamma = long_gamma[:10]

    earnings = (
        db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type == "earnings_confirmed",
            MarketEvent.source_published_at.isnot(None),
            MarketEvent.source_published_at >= now - timedelta(hours=1),
            MarketEvent.source_published_at <= now + timedelta(days=EARNINGS_LOOKAHEAD_DAYS),
        )
        .order_by(MarketEvent.source_published_at.asc())
        .limit(20)
        .all()
    )
    price_moves = (
        db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type == "price_move",
            MarketEvent.created_at >= now - timedelta(hours=24),
        )
        .order_by(MarketEvent.created_at.desc())
        .limit(10)
        .all()
    )
    impacts = _impacts_by_event(db, [event.id for event in [*earnings, *price_moves]])
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "locale": locale,
        "long_gamma": long_gamma,
        "earnings": [serialize_event(event, impacts.get(event.id, []), now) for event in earnings],
        "price_moves": [serialize_event(event, impacts.get(event.id, []), now) for event in price_moves],
        "health": health,
    }


def get_alerts(db: Session, user: User) -> dict:
    now = utcnow()
    alerts = (
        db.query(Alert)
        .filter(Alert.user_id == user.id)
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.user_id == user.id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "as_of": now.isoformat(),
        "timezone": "UTC",
        "alerts": [
            {
                "id": row.id,
                "asset": row.asset,
                "message": row.message,
                "severity": row.severity,
                "channel": row.channel,
                "status": row.status,
                "sent_at": _iso(row.sent_at),
                "created_at": _iso(row.created_at),
            }
            for row in alerts
        ],
        "deliveries": [
            {
                "id": row.id,
                "channel": row.channel,
                "status": row.status,
                "locale": row.locale,
                "attempt_count": row.attempt_count,
                "last_error": row.last_error,
                "next_retry_at": _iso(row.next_retry_at),
                "sent_at": _iso(row.sent_at),
                "created_at": _iso(row.created_at),
            }
            for row in deliveries
        ],
    }
