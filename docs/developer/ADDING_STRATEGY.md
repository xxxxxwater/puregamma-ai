# Adding a Strategy

Strategies live in `packages/strategies` and produce playbook outputs.

Strategies are research templates, not trading bots. Do not add order placement or execution logic.

## Interface

Implement `Strategy` and return `StrategyOutput` from `packages/strategies/base.py`.

Required fields:

- `strategy_name`
- `asset`
- `thesis`
- `trigger`
- `entry_condition`
- `exit_condition`
- `invalidation`
- `risk_score`
- `confidence`
- `timeframe`
- `expected_payoff`
- `required_data_sources`

## Steps

1. Add a new file in `packages/strategies`.
2. Implement `generate()`.
3. Register the strategy in `packages/strategies/registry.py`.
4. Add tests if risk, entitlement, credit, or report behavior changes.
5. Update [Signals and Playbooks](../product/SIGNALS_AND_PLAYBOOKS.md) if the strategy is user-facing.

## Safety Requirements

- Use research language such as "watch", "review", or "invalidation".
- Avoid imperatives such as "buy", "sell", or "guaranteed".
- Include risk and invalidation.
- State required data sources.
- Keep backtest claims separate from future performance.

## Example

```python
class ExampleStrategy(Strategy):
    def generate(self) -> StrategyOutput:
        return StrategyOutput(
            strategy_name="Example relative strength",
            asset="BTC",
            thesis="Research thesis.",
            trigger="Observable trigger.",
            entry_condition="Condition to review.",
            exit_condition="Condition to reduce watch.",
            invalidation="Condition that breaks thesis.",
            risk_score=50,
            confidence=0.55,
            timeframe="1-2 weeks",
            expected_payoff="Research payoff profile.",
            required_data_sources=["market"],
        )
```
