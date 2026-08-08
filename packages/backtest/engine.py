"""
NautilusTrader Backtest Engine

Replaces the previous mock engine with a NautilusTrader-integrated backtest.
Connects PureGamma data pipelines → Nautilus Catalog → Nautilus BacktestEngine.

When nautilus_trader is installed, uses the actual BacktestEngine with real data.
Otherwise falls back to a realistic simulation using the data adapter's mock_catalog.
"""

from __future__ import annotations

from typing import Any

from packages.backtest.metrics import calculate_metrics
from packages.nautilus.data_adapter import catalog_from_db, mock_catalog
from packages.nautilus.guards import assert_live_trading_disabled, live_trading_status
from packages.nautilus.result_parser import standardize_backtest_result


def _strategy_metrics(close_prices: list[float], params: dict) -> dict:
    """Deterministic, no-lookahead momentum simulation used for research metrics.

    The position for bar N is computed only from closes available at N-1. This is
    intentionally labeled as a simulation and must not be described as native
    Nautilus order execution.
    """
    if len(close_prices) < 3:
        return calculate_metrics([])
    fast = max(2, int(params.get("fast_window", 12)))
    slow = max(fast + 1, int(params.get("slow_window", 24)))
    fee_bps = max(0.0, float(params.get("fee_bps", 10.0)))
    positions: list[float] = []
    strategy_returns: list[float] = []
    previous_position = 0.0
    trades = 0
    turnover = 0.0
    for index in range(1, len(close_prices)):
        history = close_prices[:index]
        if len(history) < slow:
            position = 0.0
        else:
            fast_average = sum(history[-fast:]) / fast
            slow_average = sum(history[-slow:]) / slow
            position = 1.0 if fast_average > slow_average else 0.0
        change = abs(position - previous_position)
        if change:
            trades += 1
            turnover += change
        asset_return = close_prices[index] / close_prices[index - 1] - 1
        strategy_returns.append(previous_position * asset_return - change * fee_bps / 10_000)
        positions.append(previous_position)
        previous_position = position
    metrics = calculate_metrics(strategy_returns)
    metrics["trade_count"] = trades
    metrics["turnover"] = round(turnover, 4)
    metrics["exposure_time"] = round(sum(positions) / len(positions), 4) if positions else 0.0
    return metrics


def _nautilus_available() -> bool:
    try:
        import nautilus_trader  # noqa: F401

        return True
    except ImportError:
        return False


def _in_production() -> bool:
    from apps.api.config import get_settings

    return get_settings().app_environment.lower() == "production"


def _assert_no_mock_catalog_in_production(what: str) -> None:
    """Hard fail on any mock/synthetic catalog path in production (dev/test only)."""
    if _in_production():
        raise RuntimeError(
            f"MOCK_BACKTEST_DATA_DISABLED_IN_PRODUCTION: {what} is only available "
            "in development/test environments"
        )


class BacktestEngine:
    """Research-only backtest engine backed by NautilusTrader data catalog."""

    def run(
        self,
        strategy_name: str,
        asset: str,
        params: dict | None = None,
        *,
        db: Any = None,
        use_real_data: bool = True,
    ) -> dict:
        assert_live_trading_disabled()
        params = params or {}
        lookback = int(params.get("lookback_days", 90))
        symbols = [asset.upper()]

        # ── Build DataCatalog ──
        if use_real_data and db is not None:
            catalog = catalog_from_db(db, symbols, lookback_days=lookback)
        else:
            _assert_no_mock_catalog_in_production("nautilus mock catalog")
            catalog = mock_catalog(symbols, bar_count=lookback * 24)

        if _in_production() and (catalog.get("bar_count", 0) <= 0 or catalog.get("data_freshness") == "mock"):
            raise RuntimeError(
                "REAL_BACKTEST_DATA_UNAVAILABLE_IN_PRODUCTION: the market data "
                f"catalog has no real bars for {asset}; refusing to emit synthetic results"
            )

        # ── Run Backtest ──
        if _nautilus_available() and use_real_data and catalog["bar_count"] > 0:
            result = self._run_nautilus_backtest(strategy_name, asset, params, catalog)
        else:
            result = self._run_simulation_backtest(
                strategy_name, asset, params, catalog
            )

        return standardize_backtest_result(result)

    def _run_nautilus_backtest(
        self,
        strategy_name: str,
        asset: str,
        params: dict,
        catalog: dict,
    ) -> dict:
        """Execute backtest using the real NautilusTrader BacktestEngine."""
        engine = None
        try:
            from decimal import Decimal

            import nautilus_trader
            from nautilus_trader.backtest.engine import BacktestEngine as NTEngine
            from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
            from nautilus_trader.model.data import Bar, BarType
            from nautilus_trader.model.enums import AccountType, OmsType
            from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
            from nautilus_trader.model.instruments import CryptoPerpetual
            from nautilus_trader.model.objects import Currency, Money, Price, Quantity
            from nautilus_trader.trading.strategy import Strategy

            class CatalogReplayStrategy(Strategy):
                def __init__(self, bar_types: list):
                    super().__init__()
                    self.bar_types = bar_types
                    self.bars_processed = 0

                def on_start(self):
                    for replay_bar_type in self.bar_types:
                        self.subscribe_bars(replay_bar_type)

                def on_bar(self, bar):
                    self.bars_processed += 1

            venue = Venue("BINANCE")
            quote_currency = Currency.from_str("USDT")
            engine = NTEngine(
                config=BacktestEngineConfig(
                    logging=LoggingConfig(bypass_logging=True),
                    run_analysis=False,
                ),
            )
            engine.add_venue(
                venue=venue,
                oms_type=OmsType.NETTING,
                account_type=AccountType.MARGIN,
                base_currency=quote_currency,
                starting_balances=[Money(Decimal("100000"), quote_currency)],
            )

            precision_by_id: dict[str, tuple[int, int]] = {}
            for item in catalog["instruments"]:
                instrument_id = InstrumentId.from_str(item["id"])
                price_precision = int(item["price_precision"])
                size_precision = int(item["size_precision"])
                base_currency = Currency.from_str(item["base_currency"])
                instrument = CryptoPerpetual(
                    instrument_id=instrument_id,
                    raw_symbol=Symbol(item["id"].split(".", 1)[0].replace("-PERP", "")),
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    settlement_currency=quote_currency,
                    is_inverse=False,
                    price_precision=price_precision,
                    size_precision=size_precision,
                    price_increment=Price.from_str(
                        f"{10**-price_precision:.{price_precision}f}"
                    ),
                    size_increment=Quantity.from_str(
                        f"{10**-size_precision:.{size_precision}f}"
                    ),
                    min_notional=Money(
                        Decimal(str(item["min_notional"])), quote_currency
                    ),
                    margin_init=Decimal("0.05"),
                    margin_maint=Decimal("0.025"),
                    maker_fee=Decimal(str(item["maker_fee"])),
                    taker_fee=Decimal(str(item["taker_fee"])),
                    ts_event=0,
                    ts_init=0,
                )
                engine.add_instrument(instrument)
                precision_by_id[str(instrument_id)] = (price_precision, size_precision)

            bars_list = []
            bar_types = []
            for bar_type_str, bar_dicts in catalog["bars"].items():
                bar_type = BarType.from_str(bar_type_str)
                bar_types.append(bar_type)
                price_precision, size_precision = precision_by_id[
                    str(bar_type.instrument_id)
                ]
                for value in bar_dicts:

                    def price(key: str):
                        return Price.from_str(
                            f"{float(value[key]):.{price_precision}f}"
                        )

                    bars_list.append(
                        Bar(
                            bar_type=bar_type,
                            open=price("open"),
                            high=price("high"),
                            low=price("low"),
                            close=price("close"),
                            volume=Quantity.from_str(
                                f"{max(float(value['volume']), 0):.{size_precision}f}"
                            ),
                            ts_event=int(value["ts_event_ns"]),
                            ts_init=int(value["ts_init_ns"]),
                        )
                    )

            replay = CatalogReplayStrategy(bar_types)
            engine.add_strategy(replay)
            engine.add_data(bars_list)
            engine.run()

            close_prices = [
                float(value["close"])
                for values in catalog["bars"].values()
                for value in values
            ]
            metrics = _strategy_metrics(close_prices, params)
            return {
                "strategy_name": strategy_name,
                "asset": asset,
                "params": params,
                "metrics": metrics,
                "mode": "simulation",
                "engine": "nautilus_data_replay_with_puregamma_signal_simulation",
                "nautilus_version": getattr(nautilus_trader, "__version__", "unknown"),
                "data_freshness": catalog.get("data_freshness", "unknown"),
                "bar_count": catalog["bar_count"],
                "native_events_processed": replay.bars_processed,
                "native_iterations": engine.iteration,
                "execution_model": "no-lookahead moving-average simulation; no native orders or fills",
                "is_live": False,
                "paper_trading": False,
                "live_trading": live_trading_status(),
                "disclaimer": "Research backtest using NautilusTrader.",
            }
        except Exception as exc:
            return {
                "strategy_name": strategy_name,
                "asset": asset,
                "params": params,
                "metrics": {},
                "mode": "nautilus_error",
                "engine": "nautilus_trader",
                "error": str(exc)[:500],
                "is_live": False,
                "live_trading": live_trading_status(),
                "disclaimer": "NautilusTrader backtest failed.",
            }
        finally:
            if engine is not None:
                engine.dispose()

    def _run_simulation_backtest(
        self,
        strategy_name: str,
        asset: str,
        params: dict,
        catalog: dict,
    ) -> dict:
        """Fallback simulation using catalog bar data with realistic metrics."""
        lookback = int(params.get("lookback_days", 90))

        close_prices: list[float] = []
        for bt in catalog["bars"].values():
            for bar in bt:
                close_prices.append(float(bar["close"]))

        if not close_prices:
            _assert_no_mock_catalog_in_production("synthetic return series")
            import random

            random.seed(42)
            returns = [0.012 if i % 5 in {1, 2, 3} else -0.006 for i in range(lookback)]
        else:
            returns = [
                (close_prices[i] / close_prices[i - 1] - 1)
                if close_prices[i - 1] != 0
                else 0
                for i in range(1, len(close_prices))
            ]

        metrics = _strategy_metrics(close_prices, params) if close_prices else calculate_metrics(returns)

        is_mock_catalog = catalog.get("data_freshness", "mock") == "mock"
        return {
            "strategy_name": strategy_name,
            "asset": asset,
            "params": params,
            "metrics": metrics,
            "mode": "mock" if is_mock_catalog else "simulation",
            "engine": "puregamma_simulation_with_nautilus_catalog",
            "data_freshness": catalog.get("data_freshness", "mock"),
            "bar_count": catalog["bar_count"],
            "is_live": False,
            "paper_trading": False,
            "execution_environment": "research_mock"
            if is_mock_catalog
            else "research_simulation",
            "live_trading": live_trading_status(),
            "execution_model": "no-lookahead moving-average simulation with configured fee_bps",
            "disclaimer": "Simulation results use PureGamma data catalog.",
        }


def run_backtest_for_agent(
    db: Any,
    strategy_name: str,
    asset: str,
    params: dict | None = None,
) -> dict:
    """Convenience function for Agent tool calls.

    Returns a simplified result suitable for LLM consumption.
    """
    engine = BacktestEngine()
    result = engine.run(
        strategy_name=strategy_name,
        asset=asset,
        params=params,
        db=db,
        use_real_data=True,
    )
    return {
        "strategy": result.get("strategy_name", strategy_name),
        "asset": result.get("asset", asset),
        "total_return": result.get("metrics", {}).get("total_return", 0),
        "sharpe_ratio": result.get("metrics", {}).get("sharpe", 0),
        "max_drawdown": result.get("metrics", {}).get("max_drawdown", 0),
        "win_rate": result.get("metrics", {}).get("win_rate", 0),
        "trade_count": result.get("metrics", {}).get("trade_count", 0),
        "engine": result.get("engine", "unknown"),
        "mode": result.get("mode", "unknown"),
        "data_freshness": result.get("data_freshness", "unknown"),
        "bar_count": result.get("bar_count", 0),
        "disclaimer": result.get("disclaimer", ""),
    }
