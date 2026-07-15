from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.entitlement_service import assert_action_allowed
from packages.backtest.engines import get_backtest_engine
from packages.billing.metering import CreditReservation
from packages.database.models import BacktestRun


def run_backtest(
    db: Session,
    user_id: str,
    strategy_name: str,
    asset: str,
    params: dict | None = None,
    *,
    engine: str = "mock",
    strategy_id: str | None = None,
    idempotency_key: str | None = None,
) -> BacktestRun:
    assert_action_allowed(db, user_id, "backtest")
    normalized_engine = engine.lower().strip()
    if get_settings().app_environment.lower() == "production" and normalized_engine == "mock":
        raise ValueError("MOCK_BACKTEST_DISABLED_IN_PRODUCTION")
    request_key = idempotency_key or str(uuid.uuid4())
    scoped_key = f"backtest:{user_id}:{request_key}"
    existing = db.query(BacktestRun).filter_by(user_id=user_id, idempotency_key=scoped_key).one_or_none()
    if existing:
        return existing
    quote = quote_task(task_type="backtest", requested_model="default", async_execution=True)
    reservation = reserve_task(
        db,
        user_id,
        quote,
        f"backtest-charge:{scoped_key}",
        {"engine": normalized_engine, "asset": asset},
    )
    db.commit()
    try:
        result = get_backtest_engine(normalized_engine).run(strategy_name, asset, params, db=db)
    except Exception:
        refund_task(db, user_id, reservation, "BACKTEST_EXECUTION_FAILED")
        db.commit()
        raise
    result["requested_engine"] = engine
    result["strategy_id"] = strategy_id
    result["is_mock"] = normalized_engine == "mock"
    result["source"] = "mock" if normalized_engine == "mock" else "nautilus"
    result["idempotency_key"] = scoped_key
    settlement = settle_task(db, user_id, reservation, quote.credits, metadata={"engine": normalized_engine})
    row = BacktestRun(
        user_id=user_id,
        idempotency_key=scoped_key,
        strategy_name=strategy_name,
        asset=asset,
        params_json=params or {},
        result_json=result,
        credits_spent=settlement.actual,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
