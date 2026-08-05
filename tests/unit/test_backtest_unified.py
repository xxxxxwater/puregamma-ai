from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.api.services import unified_backtest_service as ubs
from packages.backtest import engines as engines_module
from packages.backtest.daily_data import LAB_SYMBOLS
from packages.backtest.daily_engine import run_lab_backtest
from packages.backtest.engines import (
    ExistingMockBacktestEngine,
    SyntheticDataForbiddenError,
    VectorBTBacktestEngine,
)
from packages.backtest.equity_daily import EquityDailyLoader, EquityDataUnavailable
from packages.backtest.strategy_spec import parse_spec
from packages.backtest.vectorbt_engine import run_vectorbt
from packages.backtest.strategy_compiler import StrategyCompilationError, compile_backtest_spec
from packages.database.models import BacktestCandle, BacktestRun, StrategyRiskPolicy, StrategyVersion, TradingStrategy


def _production_settings(monkeypatch):
    monkeypatch.setattr(
        "apps.api.config.get_settings",
        lambda: SimpleNamespace(app_environment="production"),
    )


def _seed_candles(db, asset: str = "BTC", bars: int = 80, start_price: float = 100.0) -> None:
    symbol = LAB_SYMBOLS[asset]
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for index in range(bars):
        ts = now - timedelta(days=bars - index)
        price = start_price + index
        db.add(
            BacktestCandle(
                id=f"test-{symbol}-{index}",
                symbol=symbol,
                interval="1d",
                ts=ts,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000.0,
                provider="binance",
                fetched_at=now,
            )
        )
    db.commit()


def _spec(assets=("BTC",), **overrides) -> dict:
    payload = {
        "name": "Test momentum strategy",
        "mode": "daily",
        "signal": "momentum",
        "assets": list(assets),
        "fast_window": 3,
        "slow_window": 5,
        "fee_bps": 10,
    }
    payload.update(overrides)
    return payload


# ── Real data coverage ────────────────────────────────────────────────


def test_lab_symbols_cover_btc_eth_sol_hype():
    assert {"BTC", "ETH", "SOL", "HYPE"} <= set(LAB_SYMBOLS)
    assert LAB_SYMBOLS["SOL"] == "SOLUSDT"
    assert LAB_SYMBOLS["HYPE"] == "HYPEUSDT"


def test_strategy_spec_accepts_new_crypto_and_equity_tickers():
    assert parse_spec(_spec(("SOL",))).assets == ["SOL"]
    assert parse_spec(_spec(("HYPE",))).assets == ["HYPE"]
    spec = parse_spec(_spec(("AAPL",)))
    assert spec.assets == ["AAPL"]
    assert spec.slippage_bps == 0.0
    with pytest.raises(ValueError):
        parse_spec(_spec(("not a ticker!",)))


# ── Production guards: no synthetic/mock data paths ───────────────────


def test_engines_synthetic_fallback_raises_in_production(monkeypatch, db):
    _production_settings(monkeypatch)

    def _failing_refresh(_db, assets, **kwargs):
        raise ConnectionError("binance unreachable")

    monkeypatch.setattr(engines_module, "refresh_daily_candles", _failing_refresh)

    engine = VectorBTBacktestEngine()
    with pytest.raises(SyntheticDataForbiddenError):
        engine.run("BTC momentum breakout", "BTC", {}, db=db)


def test_mock_engine_hard_fails_in_production(monkeypatch, db):
    _production_settings(monkeypatch)
    with pytest.raises(SyntheticDataForbiddenError):
        ExistingMockBacktestEngine().run("BTC momentum breakout", "BTC", {}, db=db)


def test_unified_service_synthetic_window_raises_in_production(monkeypatch, db):
    _production_settings(monkeypatch)

    def _failing_refresh(_db, assets, **kwargs):
        raise ConnectionError("binance unreachable")

    monkeypatch.setattr(ubs, "refresh_daily_candles", _failing_refresh)
    spec = parse_spec(_spec()).model_dump()
    end = datetime.now(timezone.utc)
    with pytest.raises(SyntheticDataForbiddenError):
        ubs._build_window(db, spec, end - timedelta(days=90), end)


# ── Agent tool routes to the unified async service ────────────────────


def test_agent_tool_returns_run_id_and_queued(monkeypatch, db, pro_user):
    from packages.agents.chat.tools import AgentToolRegistry
    from packages.workers.tasks import execute_unified_backtest

    dispatched: list[str] = []
    monkeypatch.setattr(
        "apps.api.redis_client.get_redis",
        lambda: SimpleNamespace(ping=lambda: True),
    )
    monkeypatch.setattr(execute_unified_backtest, "delay", lambda run_id: dispatched.append(run_id))

    registry = AgentToolRegistry(db, pro_user.id)
    result = registry.run_nautilus_backtest(["BTC"], lookback_days=90)

    assert result.tool_name == "run_nautilus_backtest"
    assert len(result.data) == 1
    payload = result.data[0]
    assert payload["status"] == "queued"
    assert payload["run_id"]
    assert payload["poll_url"] == f"/backtest-lab/runs/{payload['run_id']}"
    assert dispatched == [payload["run_id"]]
    row = db.get(BacktestRun, payload["run_id"])
    assert row is not None and row.status == "queued" and row.user_id == pro_user.id
    assert "run_id" in result.summary


# ── Lifecycle: queued → running → completed / cancelled ───────────────


def test_unified_run_lifecycle_with_real_seeded_candles(monkeypatch, db, pro_user):
    _seed_candles(db, "BTC", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    observed_statuses: list[str] = []
    real_run_vectorbt = ubs.run_vectorbt

    def _wrapped(spec, window, **kwargs):
        row = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).first()
        observed_statuses.append(row.status)
        return real_run_vectorbt(spec, window, **kwargs)

    monkeypatch.setattr(ubs, "run_vectorbt", _wrapped)

    row = ubs.create_unified_run(db, pro_user.id, _spec(), window_days=90)
    assert row.status == "queued"
    assert row.credits_reserved == 50
    assert row.assumptions_json["lookahead_guard"] == "signals executed on next bar close"

    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "completed"
    assert observed_statuses == ["running"]  # running state was persisted mid-flight
    assert row.completed_at is not None

    result = row.result_json
    assert result["equity_curve"] and result["benchmark_curve"] and result["drawdown_curve"]
    assert "trades" in result and "positions" in result
    assert result["charts"]["equity"]["data"]

    assumptions = row.assumptions_json
    assert assumptions["fee_bps"] == 10.0
    assert assumptions["slippage_bps"] == 0.0
    assert assumptions["sample_start"] and assumptions["sample_end"]
    assert assumptions["benchmark"] == "equal_weight_buy_hold"
    assert assumptions["data_source"] == "binance"
    assert assumptions["interval"] == "1d"
    assert assumptions["lookahead_guard"] == "signals executed on next bar close"
    assert row.data_snapshot_json["provider"] == "binance"


def test_cancel_queued_run_refunds_and_is_idempotent(db, pro_user):
    row = ubs.create_unified_run(db, pro_user.id, _spec(), window_days=90)
    assert row.status == "queued"

    cancelled = ubs.cancel_unified_run(db, pro_user.id, row.id)
    assert cancelled.status == "cancelled"
    assert cancelled.error_json["code"] == "CANCELLED_BY_USER"

    again = ubs.cancel_unified_run(db, pro_user.id, row.id)
    assert again.id == cancelled.id and again.status == "cancelled"

    # A cancelled run picked up by a worker must not execute.
    untouched = ubs.execute_unified_run(db, row.id)
    assert untouched.status == "cancelled"
    assert not (untouched.result_json or {}).get("equity_curve")


def test_cancel_completed_run_rejected(monkeypatch, db, pro_user):
    _seed_candles(db, "BTC", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    row = ubs.create_unified_run(db, pro_user.id, _spec(), window_days=90)
    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "completed"
    with pytest.raises(ValueError):
        ubs.cancel_unified_run(db, pro_user.id, row.id)


def test_cancel_running_run_wins_over_worker_completion(monkeypatch, db, pro_user):
    """A cancel landing while the engine runs must survive: the worker never
    overwrites it with a completion and the reservation is refunded exactly
    once (no double charge, no charge at all)."""
    from packages.database.models import User

    _seed_candles(db, "BTC", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    real_run_vectorbt = ubs.run_vectorbt

    def _cancel_midflight(spec, window, **kwargs):
        row = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).first()
        ubs.cancel_unified_run(db, row.user_id, row.id)
        return real_run_vectorbt(spec, window, **kwargs)

    monkeypatch.setattr(ubs, "run_vectorbt", _cancel_midflight)
    balance_before = db.get(User, pro_user.id).credit_balance
    row = ubs.create_unified_run(db, pro_user.id, _spec(), window_days=90)
    assert db.get(User, pro_user.id).credit_balance == balance_before - 50

    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "cancelled"
    assert row.error_json["code"] == "CANCELLED_BY_USER"
    assert not (row.result_json or {}).get("equity_curve")
    assert row.credits_spent == 0
    assert db.get(User, pro_user.id).credit_balance == balance_before  # refunded exactly once


def test_hype_candles_come_from_hyperliquid(monkeypatch, db):
    """HYPE is not listed on Binance spot; its daily candles must come from
    the Hyperliquid info API and be labeled honestly."""
    from packages.backtest import daily_data

    calls: list[str] = []

    def _fake_binance(symbol, start_ms, end_ms):
        calls.append(f"binance:{symbol}")
        raise AssertionError("HYPE must not be fetched from Binance spot")

    def _fake_hyperliquid(coin, start_ms, end_ms):
        calls.append(f"hyperliquid:{coin}")
        day = 86_400_000
        return [[start_ms + index * day, "10", "11", "9", "10.5", "1000"] for index in range(5)]

    monkeypatch.setattr(daily_data, "_fetch_klines", _fake_binance)
    monkeypatch.setattr(daily_data, "_fetch_hyperliquid_daily", _fake_hyperliquid)
    stats = daily_data.refresh_daily_candles(db, ["HYPE"])
    assert calls == ["hyperliquid:HYPE"]
    assert stats["HYPEUSDT"]["upserted"] == 5
    rows = db.query(BacktestCandle).filter_by(symbol="HYPEUSDT").all()
    assert rows and all(row.provider == "hyperliquid" for row in rows)
    assert daily_data.provider_for_asset("HYPE") == "hyperliquid"
    assert daily_data.provider_for_asset("BTC") == "binance"


def test_hype_backtest_labeled_hyperliquid(monkeypatch, db, pro_user):
    _seed_candles(db, "HYPE", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    row = ubs.create_unified_run(db, pro_user.id, _spec(assets=("HYPE",)), window_days=90)
    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "completed"
    assert row.result_json["data_sources"]["HYPE"] == "hyperliquid"
    assert row.assumptions_json["data_sources"]["HYPE"] == "hyperliquid"


def test_rest_entry_honors_slippage_bps(monkeypatch, api_client, db, pro_user):
    """POST /backtest must plumb slippage_bps into the spec and assumptions
    (regression: the REST entry silently dropped it)."""
    from tests.conftest import auth_headers

    _seed_candles(db, "BTC", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    response = api_client.post(
        "/backtest",
        json={"strategy_name": "slip test", "asset": "BTC", "engine": "vectorbt", "params": {"slippage_bps": 25, "lookback_days": 90}},
        headers=auth_headers(pro_user),
    )
    assert response.status_code == 200, response.text
    backtest = response.json()["backtest"]
    assert backtest["status"] == "completed"
    assert backtest["assumptions"]["slippage_bps"] == 25.0


# ── Lookahead regression: signal at bar t executes at bar t+1 close ───


def _lookahead_probe_window():
    """Flat 100s, a moderate lift on bar 40 (signal triggers), a +50% jump on
    bar 41, then flat. Same-bar execution would capture the +50% jump; correct
    next-bar-close execution cannot."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    closes = [100.0] * 40 + [110.0, 165.0] + [165.0] * 9
    return {"BTC": [{"ts": start + timedelta(days=index), "close": price} for index, price in enumerate(closes)]}, closes


def test_vectorbt_never_executes_same_bar():
    window, closes = _lookahead_probe_window()
    spec = {"name": "probe", "assets": ["BTC"], "signal": "momentum", "fast_window": 3, "slow_window": 6, "fee_bps": 0}
    result = run_vectorbt(spec, window)

    # The signal first fires using the close of bar 40; execution happens at
    # the close of bar 41, so the +50% jump between bars 40→41 is never earned.
    assert result["metrics"]["final_equity"] == pytest.approx(100_000.0)
    assert result["trades"], "expected at least one trade"
    first_trade_ts = result["trades"][0]["ts"]
    bars = window["BTC"]
    assert first_trade_ts == bars[41]["ts"].isoformat()

    # Prove the crafted series is discriminating: same-bar execution WOULD
    # have captured the jump and ended ~50% higher.
    same_bar_final = 100_000.0 * (closes[41] / closes[40])
    assert result["metrics"]["final_equity"] != pytest.approx(same_bar_final)


def test_daily_engine_never_executes_same_bar():
    window, _ = _lookahead_probe_window()
    spec = parse_spec(_spec(fast_window=3, slow_window=6, fee_bps=0))
    result = run_lab_backtest(spec, window)
    assert result.equity_curve[-1]["equity"] == pytest.approx(1.0)
    assert result.trades[0]["ts"] == window["BTC"][41]["ts"].isoformat()


# ── Backtest → Strategy version ───────────────────────────────────────


def test_save_as_strategy_is_idempotent(monkeypatch, db, pro_user):
    _seed_candles(db, "BTC", bars=80)
    monkeypatch.setattr(ubs, "refresh_daily_candles", lambda _db, assets: {})
    row = ubs.create_unified_run(db, pro_user.id, _spec(), window_days=90)
    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "completed"

    first = ubs.save_run_as_strategy(db, pro_user.id, row.id)
    assert first["created"] is True
    strategy = first["strategy"]
    assert strategy.status == "DRAFT"
    assert strategy.execution_mode == "PAPER"
    version = first["version"]
    assert version.status == "VALIDATED"
    assert version.draft_json["backtest_spec"]["assets"] == ["BTC"]
    assert version.draft_json["instruments"] == ["BTCUSDT"]
    assert version.draft_json["venues"] == ["MOCK"]
    assert version.draft_json["timeframe"] == "1d"
    assert version.draft_json["strategy_type"] == "DirectionalStrategy"
    assert version.draft_json["entry_rules"]
    assert version.draft_json["exit_rules"]
    assert version.draft_json["position_sizing"]["method"] == "fractional_notional"
    assert version.draft_json["risk_policy"]["stale_market_blocks_opening"] is True
    assert version.draft_json["execution_mode"] == "PAPER"
    assert version.draft_json["run_id"] == row.id
    assert db.query(StrategyRiskPolicy).filter_by(strategy_id=strategy.id, strategy_version=1).count() == 1

    db.refresh(row)
    assert row.strategy_id == strategy.id

    second = ubs.save_run_as_strategy(db, pro_user.id, row.id)
    assert second["created"] is False
    assert second["strategy"].id == strategy.id
    assert db.query(TradingStrategy).filter_by(user_id=pro_user.id).count() == 1
    assert db.query(StrategyVersion).filter_by(strategy_id=strategy.id).count() == 1


def test_backtest_spec_compiles_to_runtime_strategy_contract():
    compiled = compile_backtest_spec(
        _spec(assets=("BTC",), stop_loss_pct=0.05),
        assumptions={"fee_bps": 10, "slippage_bps": 2, "sample_end": "2026-08-04T00:00:00+00:00"},
        result={"metrics": {"max_drawdown": 0.12}},
        window_days=90,
    ).model_dump(mode="json")

    assert compiled["instruments"] == ["BTCUSDT"]
    assert compiled["venues"] == ["MOCK"]
    assert compiled["strategy_type"] == "DirectionalStrategy"
    assert compiled["output_contract"] == "OrderIntent"
    assert compiled["entry_rules"][0]["lookahead_guard"] == "signals executed on next bar close"
    assert compiled["risk_policy"]["max_leverage"] == 1.0
    assert compiled["backtest_config"]["fee_bps"] == 10.0


def test_cross_sectional_backtest_cannot_be_saved_as_executable_strategy():
    with pytest.raises(StrategyCompilationError):
        compile_backtest_spec(
            _spec(assets=("BTC", "ETH"), mode="cross_sectional", signal="relative_strength")
        )


# ── US equity daily loader: keyed chain or explicit UNAVAILABLE ───────


def test_equity_loader_uses_keyed_provider(monkeypatch):
    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "historical": [
                    {"date": "2026-07-02", "open": 101, "high": 103, "low": 99, "close": 102, "volume": 10},
                    {"date": "2026-07-01", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 12},
                ]
            }

    monkeypatch.setattr("packages.backtest.equity_daily.httpx.get", lambda *args, **kwargs: _Response())
    loader = EquityDailyLoader(fmp_api_key="test-key", alpha_vantage_api_key="", massive_api_key="")
    assert loader.configured_providers == ["fmp"]
    bars = loader.load_daily("AAPL", datetime(2026, 6, 1, tzinfo=timezone.utc), datetime(2026, 7, 3, tzinfo=timezone.utc))
    assert [bar["close"] for bar in bars] == [100.0, 102.0]
    assert bars[0]["ts"] < bars[1]["ts"]


def test_equity_loader_unavailable_without_keys(monkeypatch):
    for var in ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "MASSIVE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    loader = EquityDailyLoader()
    assert loader.configured_providers == []
    with pytest.raises(EquityDataUnavailable) as excinfo:
        loader.load_daily("AAPL", datetime(2026, 6, 1, tzinfo=timezone.utc), datetime(2026, 7, 3, tzinfo=timezone.utc))
    assert "AAPL" in str(excinfo.value)
    assert any("no API key configured" in reason for reason in excinfo.value.reasons)


def test_equity_backtest_marks_unavailable_never_synthetic(monkeypatch, db, pro_user):
    for var in ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "MASSIVE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    row = ubs.create_unified_run(db, pro_user.id, _spec(("AAPL",)), window_days=90)
    with pytest.raises(EquityDataUnavailable):
        ubs.execute_unified_run(db, row.id)
    row = db.get(BacktestRun, row.id)
    assert row.status == "failed"
    assert row.error_json["code"] == "EQUITY_DATA_UNAVAILABLE"
    assert "synthetic" not in str(row.error_json).lower()


def test_equity_backtest_completes_with_keyed_provider(monkeypatch, db, pro_user):
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    historical = [
        {
            "date": (start + timedelta(days=index)).date().isoformat(),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100 + index,
            "volume": 1000,
        }
        for index in range(60)
    ]

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"historical": list(reversed(historical))}

    monkeypatch.setattr("packages.backtest.equity_daily.httpx.get", lambda *args, **kwargs: _Response())
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    row = ubs.create_unified_run(db, pro_user.id, _spec(("AAPL",)), window_days=365 * 3)
    row = ubs.execute_unified_run(db, row.id)
    assert row.status == "completed"
    assert row.data_snapshot_json["providers"] == {"AAPL": "equity:fmp"}
    assert row.assumptions_json["data_source"] == "equity"
    assert row.result_json["equity_curve"]


def test_short_window_adapts_slow_window():
    from packages.backtest.vectorbt_engine import run_vectorbt

    now = datetime.now(timezone.utc)
    window = {
        "BTC": [{"ts": now - timedelta(days=29 - i), "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 100 + i * 0.5, "volume": 1000} for i in range(29)],
    }
    spec = {"assets": ["BTC"], "fast_window": 12, "slow_window": 40, "signal": "momentum", "long_short": False, "fee_bps": 10}
    result = run_vectorbt(spec, window)
    assert result["equity_curve"]
    assert result["windows_adjusted"]["slow"] == 27
    assert result["windows_adjusted"]["fast"] == 12


def test_week_window_runs_with_minimal_bars():
    from packages.backtest.vectorbt_engine import run_vectorbt

    now = datetime.now(timezone.utc)
    window = {
        "BTC": [{"ts": now - timedelta(days=6 - i), "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 100 + i * 0.5, "volume": 1000} for i in range(7)],
    }
    spec = {"assets": ["BTC"], "fast_window": 12, "slow_window": 26, "signal": "momentum", "long_short": False, "fee_bps": 10}
    result = run_vectorbt(spec, window)
    assert result["equity_curve"]
    assert result["windows_adjusted"]["slow"] == 5
