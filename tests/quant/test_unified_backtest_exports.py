from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace

from apps.api.services.unified_backtest_service import export_run
from packages.database.models import BacktestRun


def test_completed_backtest_export_costs_50_credits_and_keeps_paths_relative(db, max_user, monkeypatch):
    run = BacktestRun(
        user_id=max_user.id,
        idempotency_key="export-cost-test",
        status="completed",
        engine="vectorbt",
        strategy_name="BTC trend",
        asset="BTC",
        params_json={},
        spec_json={"spec": {"name": "BTC trend", "mode": "daily"}},
        result_json={"metrics": {}, "trades": [{"ts": "2025-01-01T00:00:00+00:00", "asset": "BTC", "from": 0, "to": 1}], "equity_curve": []},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    artifact_dir = Path.cwd() / ".test-backtest-artifacts" / run.id
    monkeypatch.setattr(
        "packages.backtest.artifacts.get_settings",
        lambda: SimpleNamespace(backtest_artifact_dir=str(artifact_dir)),
    )
    try:
        before = max_user.credit_balance
        artifact = export_run(db, max_user.id, run.id, "json")
        db.refresh(max_user)

        assert artifact.credits_spent == 50
        assert max_user.credit_balance == before - 50
        assert not Path(artifact.relative_path).is_absolute()
        assert (artifact_dir / artifact.relative_path).is_file()
    finally:
        shutil.rmtree(artifact_dir, ignore_errors=True)
