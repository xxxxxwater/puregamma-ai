from __future__ import annotations

from apps.api.services.runtime_sync_service import sync_runtime_account
from packages.database.models import (
    AccountSnapshot,
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    SignalEvent,
    StrategyRun,
    TradingAccount,
    TradingStrategy,
)
from tests.conftest import auth_headers


class FakeRuntimeState:
    def __init__(self, account_id: str, runtime_run_id: str):
        self.account_id = account_id
        self.runtime_run_id = runtime_run_id

    def account_state(self, account_id: str):
        assert account_id == self.account_id
        return {
            "account": {
                "account_id": account_id,
                "balance": 100000,
                "equity": 100010,
                "available_margin": 99000,
                "daily_pnl": 10,
                "drawdown": 0,
                "exposure": 1000,
                "stale": False,
            },
            "positions": [
                {
                    "account_id": account_id,
                    "instrument": "BTCUSDT",
                    "quantity": 0.01,
                    "side": "LONG",
                    "average_price": 60000,
                    "mark_price": 61000,
                    "unrealized_pnl": 10,
                    "realized_pnl": 0,
                    "leverage": 1,
                    "run_id": self.runtime_run_id,
                    "updated_at": "2026-07-11T00:01:00+00:00",
                }
            ],
            "orders": [
                {
                    "client_order_id": "pg-phase3-order",
                    "sequence": 5,
                    "run_id": self.runtime_run_id,
                    "account_id": account_id,
                    "instrument": "BTCUSDT",
                    "venue": "MOCK",
                    "side": "BUY",
                    "quantity": 0.01,
                    "notional": 600,
                    "leverage": 1,
                    "order_type": "MARKET",
                    "state": "FILLED",
                    "filled_quantity": 0.01,
                    "remaining_quantity": 0,
                    "average_price": 60000,
                    "exchange_order_id": "mock-phase3",
                }
            ],
        }

    def events(self, limit=500):
        return {
            "events": [
                {
                    "id": 42,
                    "event_type": "STRATEGY_SIGNAL",
                    "aggregate_id": self.runtime_run_id,
                    "created_at": "2026-07-11T00:00:02+00:00",
                    "payload": {
                        "run_id": self.runtime_run_id,
                        "asset": "BTC",
                        "direction": "LONG",
                        "change": 0.01,
                        "threshold": 0.002,
                        "provider": "hyperliquid_public",
                        "source_timestamp": "2026-07-11T00:00:01+00:00",
                    },
                }
            ]
        }


def test_runtime_state_sync_is_idempotent(db, pro_user):
    account = TradingAccount(
        user_id=pro_user.id,
        name="Phase 3 Paper",
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
        permissions_json={"paper_order": True, "live_order": False},
    )
    strategy = TradingStrategy(
        user_id=pro_user.id,
        name="Phase 3 strategy",
        description="test",
        status="ACTIVE",
        current_version=1,
        execution_mode="PAPER",
    )
    db.add_all([account, strategy])
    db.flush()
    run = StrategyRun(
        user_id=pro_user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        account_id=account.id,
        runtime_run_id="runtime-phase3",
        execution_mode="PAPER",
        status="RUNNING",
    )
    db.add(run)
    db.commit()
    runtime = FakeRuntimeState(account.id, run.runtime_run_id)

    first = sync_runtime_account(db, account, runtime=runtime)
    second = sync_runtime_account(db, account, runtime=runtime)

    assert first == {"account_id": account.id, "snapshots": 1, "orders": 1, "signals": 1}
    assert second == {"account_id": account.id, "snapshots": 0, "orders": 0, "signals": 0}
    assert db.query(AccountSnapshot).filter_by(account_id=account.id).count() == 1
    assert db.query(PositionSnapshot).filter_by(account_id=account.id).count() == 1
    assert db.query(OrderIntent).filter_by(account_id=account.id).count() == 1
    assert db.query(OrderJournal).filter_by(account_id=account.id).count() == 1
    signal = db.query(SignalEvent).filter_by(run_id=run.id).one()
    assert signal.source_urls == ["https://api.hyperliquid.xyz/info"]


def test_runtime_sync_rejects_foreign_account(api_client, db, pro_user, normal_user):
    account = TradingAccount(
        user_id=normal_user.id,
        name="Foreign Paper",
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
        permissions_json={"paper_order": True},
    )
    db.add(account)
    db.commit()

    response = api_client.post(
        "/trading/runtime/sync",
        json={"account_id": account.id},
        headers=auth_headers(pro_user),
    )

    assert response.status_code == 404
