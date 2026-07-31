# Nautilus Validation

Current repository status:

- `packages/nautilus/` previously did not exist.
- `packages/backtest/engine.py` used a deterministic mock return stream.
- Product docs already state that NautilusTrader runtime is planned and current backend uses mock backtest behavior.

## Added Validation Layer

The repository now includes a minimal `packages/nautilus` research adapter:

- `guards.py`: live trading status is always disabled.
- `result_parser.py`: standardizes metrics and prevents mock output from being labeled live.

## Requirements Mapping

| Requirement | Status |
| --- | --- |
| Nautilus as research/backtest/paper layer only | Enforced by docs and guard. |
| Live trading disabled by default | Enforced by `LIVE_TRADING_ENABLED = False`. |
| OHLCV/funding/OI/events bridge preserves timestamps | Required by docs; real bridge still future work. |
| `strategy_bridge` should not drop timestamps | Required; bridge not yet implemented. |
| Result parser outputs standard metrics | Implemented in `packages/nautilus/result_parser.py`. |
| Mock engine not labeled real backtest | Implemented via `mode: mock` and `execution_environment: research_mock`. |
| Paper trading is not real trading | Documented and parser separates `paper_trading` from `is_live`. |

## Validation Result

PureGamma can use current backtest output for UI/demo research only. It is not ready for production-grade NautilusTrader claims until a real Nautilus adapter, timestamped data bridge, fills model, and venue-specific costs are implemented.
