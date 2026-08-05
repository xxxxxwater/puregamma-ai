"""Backtest lab orchestration: context-aware spec generation and execution."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import assert_action_allowed
from packages.agents.llm_client import LLMClient
from packages.agents.strategy_prompt import build_strategy_prompt
from packages.backtest.daily_data import candle_coverage, load_candle_window, refresh_daily_candles
from packages.backtest.daily_engine import downsample_equity, run_lab_backtest
from packages.backtest.strategy_spec import DEFAULT_SPEC, StrategySpec, parse_spec
from packages.database.models import AgentMessage, BacktestLabRun, utcnow

logger = logging.getLogger(__name__)

LAB_DAILY_RUN_LIMIT = 5
LAB_DEFAULT_WINDOW_DAYS = 30
ASSUMPTIONS = {
    "execution": "next-bar close-to-close, no look-ahead",
    "data": "binance 1d klines (shared dataset)",
    "costs": "fee_bps per unit turnover",
    "fill_model": "hypothetical; no slippage beyond configured fees",
    "live_trading": False,
}


class LabRateLimited(Exception):
    pass


def _user_research_context(db: Session, user_id: str, *, limit: int = 8) -> list[str]:
    """Recent secretary/agent utterances used as strategy-generation context."""
    rows = (
        db.query(AgentMessage)
        .filter(AgentMessage.user_id == user_id, AgentMessage.role == "user")
        .order_by(AgentMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    notes: list[str] = []
    for row in rows:
        text = re.sub(r"\s+", " ", str(row.content or "")).strip()
        if text:
            notes.append(text[:220])
    return notes


def generate_lab_spec(
    db: Session,
    user_id: str,
    idea: str,
    *,
    use_memory: bool,
    locale: str,
) -> tuple[StrategySpec, dict]:
    notes = _user_research_context(db, user_id) if use_memory else []
    prompt = build_strategy_prompt(idea, locale=locale, secretary_notes=notes, conversation_notes=[])
    raw = LLMClient().complete("backtest_lab_strategy_spec", prompt, locale=locale, user_id=user_id, db=db)
    candidate = raw.strip()
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not match:
        logger.warning("backtest_lab_spec_parse_fallback user_id=%s", user_id)
        return DEFAULT_SPEC, {"llm_raw": candidate[:400], "fallback": True, "context_notes": len(notes)}
    try:
        spec = parse_spec(json.loads(match.group(0)))
    except Exception as exc:
        logger.warning("backtest_lab_spec_invalid user_id=%s error=%s", user_id, type(exc).__name__)
        return DEFAULT_SPEC, {"llm_raw": candidate[:400], "fallback": True, "context_notes": len(notes)}
    return spec, {"llm_raw": None, "fallback": False, "context_notes": len(notes)}


def _runs_today(db: Session, user_id: str) -> int:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(BacktestLabRun).filter(BacktestLabRun.user_id == user_id, BacktestLabRun.created_at >= day_start).count()


def run_lab(
    db: Session,
    user_id: str,
    spec_payload: dict,
    *,
    window_days: int = LAB_DEFAULT_WINDOW_DAYS,
    idempotency_key: str | None = None,
    context_meta: dict | None = None,
) -> BacktestLabRun:
    assert_action_allowed(db, user_id, "backtest")
    if _runs_today(db, user_id) >= LAB_DAILY_RUN_LIMIT:
        raise LabRateLimited(f"Daily backtest limit reached ({LAB_DAILY_RUN_LIMIT})")
    spec = parse_spec(spec_payload)
    request_key = idempotency_key or str(uuid.uuid4())
    scoped_key = f"backtest-lab:{user_id}:{request_key}"
    existing = db.query(BacktestLabRun).filter_by(idempotency_key=scoped_key).one_or_none()
    if existing:
        return existing

    quote = quote_task(task_type="backtest", requested_model="default", async_execution=True)
    reservation = reserve_task(db, user_id, quote, f"backtest-lab-charge:{scoped_key}", {"mode": spec.mode, "assets": spec.assets})
    db.commit()
    try:
        refresh_daily_candles(db, spec.assets)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, min(window_days, LAB_DEFAULT_WINDOW_DAYS)))
        window = load_candle_window(db, spec.assets, start, end)
        result = run_lab_backtest(spec, window)
        coverage = candle_coverage(db)
    except Exception:
        refund_task(db, user_id, reservation, "BACKTEST_LAB_EXECUTION_FAILED")
        db.commit()
        raise
    settlement = settle_task(db, user_id, reservation, quote.credits, metadata={"mode": spec.mode})
    row = BacktestLabRun(
        user_id=user_id,
        idempotency_key=scoped_key,
        status="completed",
        mode=spec.mode,
        spec_json=spec.model_dump(),
        symbols_json=spec.assets,
        window_start=start,
        window_end=end,
        performance_json=result.metrics,
        equity_json=downsample_equity(result.equity_curve),
        assumptions_json={**ASSUMPTIONS, "fee_bps": spec.fee_bps, "coverage": coverage},
        context_used_json=context_meta or {},
        credits_spent=settlement.actual,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def serialize_lab_run(row: BacktestLabRun) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "mode": row.mode,
        "spec": row.spec_json,
        "symbols": row.symbols_json,
        "window": {
            "start": row.window_start.isoformat() if row.window_start else None,
            "end": row.window_end.isoformat() if row.window_end else None,
        },
        "performance": row.performance_json,
        "equity_curve": row.equity_json,
        "assumptions": row.assumptions_json,
        "context_used": row.context_used_json,
        "credits_spent": row.credits_spent,
        "created_at": row.created_at.isoformat(),
    }


def list_lab_runs(db: Session, user_id: str, *, limit: int = 20) -> list[BacktestLabRun]:
    return (
        db.query(BacktestLabRun)
        .filter(BacktestLabRun.user_id == user_id)
        .order_by(BacktestLabRun.created_at.desc())
        .limit(min(limit, 50))
        .all()
    )


def lab_status(db: Session) -> dict:
    return {
        "coverage": candle_coverage(db),
    }
