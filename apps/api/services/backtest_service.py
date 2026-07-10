from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.services.credit_service import consume_credits
from apps.api.services.entitlement_service import assert_action_allowed
from packages.backtest.engine import BacktestEngine
from packages.billing.credits import cost_for
from packages.database.models import BacktestRun


def run_backtest(db: Session, user_id: str, strategy_name: str, asset: str, params: dict | None = None) -> BacktestRun:
    assert_action_allowed(db, user_id, "backtest")
    spent = cost_for("backtest")
    consume_credits(db, user_id, "backtest", spent)
    result = BacktestEngine().run(strategy_name, asset, params, db=db)
    row = BacktestRun(
        user_id=user_id,
        strategy_name=strategy_name,
        asset=asset,
        params_json=params or {},
        result_json=result,
        credits_spent=spent,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
