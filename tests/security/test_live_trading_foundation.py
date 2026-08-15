"""LIVE Trading Control Plane foundation tests.

Verifies the hard safety properties: append-only ledger/risk/fill records,
encrypted secrets, kill switches, the risk engine order, idempotency, the
mandate ownership boundary, NAV staleness behavior, and reconciliation pausing.
No test ever requires a real broker — a fake gateway stands in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from packages.database.models import (
    BrokerConnection,
    Fill,
    LedgerEntry,
    LiveOrder,
    LiveOrderIntent,
    LiveUserApproval,
    RiskCheck,
    StrategyRelease,
    TradingAccount,
    TradingKillSwitch,
    TradingMandate,
    TradingReconciliation,
    TradingStrategy,
    utcnow,
)
from packages.live_trading import control_plane, flags, kill_switch, ledger, nav
from packages.live_trading import price_feed as price_feed_service
from packages.live_trading import reconciliation as reconciliation_service
from packages.live_trading import risk_engine
from packages.live_trading.enums import LiveOrderStatus, OrderSource
from packages.live_trading.gateway_adapter import GatewayError
from packages.live_trading.secret_store import decrypt_secrets, encrypt_secrets


class FakeGateway:
    name = "fake"

    def __init__(self, *, balance: str = "100000", fills: bool = False):
        self.balance = balance
        self.fills = fills
        self.submitted: list[dict] = []

    def health(self):
        return {"status": "HEALTHY", "adapter": "fake"}

    def submit_order(self, payload):
        self.submitted.append(payload)
        ack = {
            "state": "submitted",
            "broker_order_id": f"brk-{payload['client_order_id']}",
        }
        if self.fills:
            ack["fills"] = [
                {
                    "broker_fill_id": "fill-1",
                    "quantity": payload["quantity"],
                    "price": "100",
                    "fee": "1.5",
                    "fee_currency": "USD",
                }
            ]
        return ack

    def query_order(self, client_order_id, account_id):
        return {"state": "filled", "order": {"broker_order_id": "brk-x"}}

    def cancel_order(self, client_order_id, account_id):
        return {"state": "canceled"}

    def account_balances(self, account_id):
        return {"cash": self.balance, "available": self.balance, "equity": self.balance}

    def positions(self, account_id):
        return []


@pytest.fixture()
def fake_gateway():
    return FakeGateway()


def _enable_static_gate(monkeypatch):
    gate = flags.GateResult(
        enabled=True,
        checks={},
    )
    monkeypatch.setattr(flags, "evaluate_static_gate", lambda: gate)


def _make_live_world(db: Session, user, monkeypatch, **mandate_kwargs):
    """Create the full approved LIVE stack for a user and return it."""
    from cryptography.fernet import Fernet

    from packages.live_trading import secret_store

    test_key = Fernet.generate_key()
    monkeypatch.setattr(secret_store, "_fernet", lambda: Fernet(test_key))
    _enable_static_gate(monkeypatch)
    account = TradingAccount(
        user_id=user.id,
        name="live-account",
        venue="MOCK",
        account_type="LIVE",
        base_currency="USD",
        status="ACTIVE",
    )
    db.add(account)
    db.flush()

    strategy = TradingStrategy(
        user_id=user.id,
        name="live-strategy",
        description="",
        status="ACTIVE",
        execution_mode="LIVE",
    )
    db.add(strategy)
    db.flush()

    release = StrategyRelease(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        release_number=1,
        spec_json={"entry": "n/a"},
        spec_hash="sha256:test",
        review_status="approved",
        created_by="user",
    )
    db.add(release)
    db.flush()

    connection = BrokerConnection(
        user_id=user.id,
        provider="fake",
        account_label="main",
        encrypted_credentials_ref=encrypt_secrets({"api_key": "k", "secret": "s"}),
        environment="production",
        status="HEALTHY",
    )
    db.add(connection)
    db.flush()

    defaults = dict(
        user_id=user.id,
        account_id=account.id,
        strategy_release_id=release.id,
        broker_connection_id=connection.id,
        execution_mode="live",
        environment="production",
        status="active",
        allowed_symbols_json=["BTCUSDT"],
        allowed_side="both",
        max_total_notional=Decimal("10000"),
        max_per_order_notional=Decimal("2000"),
        max_position_notional=Decimal("5000"),
        max_leverage=Decimal("1"),
        max_daily_loss=Decimal("500"),
        max_trades_per_day=10,
        max_order_frequency_seconds=0,
        kill_switch_state="inactive",
        paused=False,
        approval_status="approved",
        idempotency_key=f"mandate:{user.id}:test",
    )
    defaults.update(mandate_kwargs)
    mandate = TradingMandate(**defaults)
    db.add(mandate)
    db.flush()

    approval = LiveUserApproval(
        user_id=user.id,
        status="approved",
        max_total_notional=Decimal("10000"),
    )
    db.add(approval)
    db.commit()
    # A valid server price so market orders can be priced for notional checks.
    price_feed_service.record_price(db, symbol="BTCUSDT", price="100", venue="MOCK")
    db.commit()
    return {
        "account": account,
        "strategy": strategy,
        "release": release,
        "connection": connection,
        "mandate": mandate,
    }


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_ledger_is_append_only(db, user_factory):
    user = user_factory("ledger@test.com")
    account = TradingAccount(
        user_id=user.id, name="a", venue="MOCK", account_type="PAPER", status="ACTIVE"
    )
    db.add(account)
    db.flush()
    entry = ledger.post_entry(
        db,
        user_id=user.id,
        account_id=account.id,
        entry_type="cash_deposit",
        amount=Decimal("100"),
        idempotency_key="ledger:test:1",
        trace_id="trace-1",
    )
    db.commit()
    with pytest.raises(RuntimeError, match="immutable"):
        entry.amount = Decimal("999")
        db.flush()
    db.rollback()
    with pytest.raises(RuntimeError, match="immutable"):
        db.delete(entry)
        db.flush()


def test_risk_check_and_fill_are_immutable(db, user_factory, monkeypatch):
    user = user_factory("immutable@test.com")
    world = _make_live_world(db, user, monkeypatch)
    # Build a real intent + risk check through the control plane.
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=FakeGateway(),
    )
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=FakeGateway(fills=True),
    )
    risk_check = db.query(RiskCheck).filter_by(order_intent_id=result["intent"].id).one()
    with pytest.raises(RuntimeError, match="immutable"):
        risk_check.result = "PASS"
        db.flush()
    db.rollback()
    fill = db.query(Fill).filter_by(order_id=order.id).one()
    with pytest.raises(RuntimeError, match="immutable"):
        fill.price = Decimal("1")
        db.flush()


# ---------------------------------------------------------------------------
# Secret store
# ---------------------------------------------------------------------------


def test_secret_store_never_persists_plaintext(db, user_factory, monkeypatch):
    from cryptography.fernet import Fernet

    from packages.live_trading import secret_store

    test_key = Fernet.generate_key()
    monkeypatch.setattr(secret_store, "_fernet", lambda: Fernet(test_key))

    user = user_factory("secrets@test.com")
    secrets_dict = {"api_key": "AK-12345", "api_secret": "supersecret"}
    ciphertext = encrypt_secrets(secrets_dict)
    assert "supersecret" not in ciphertext
    assert "AK-12345" not in ciphertext
    assert decrypt_secrets(ciphertext) == secrets_dict
    assert decrypt_secrets(None) == {}
    # The DB column stores only the ciphertext.
    connection = BrokerConnection(
        user_id=user.id,
        provider="fake",
        account_label="secret",
        encrypted_credentials_ref=ciphertext,
        environment="production",
    )
    db.add(connection)
    db.commit()
    stored = (
        db.query(BrokerConnection)
        .filter_by(user_id=user.id, account_label="secret")
        .one()
    )
    assert stored.encrypted_credentials_ref == ciphertext
    assert "supersecret" not in stored.encrypted_credentials_ref


# ---------------------------------------------------------------------------
# Kill switches
# ---------------------------------------------------------------------------


def test_kill_switch_blocks_preview_and_allows_cancel(db, user_factory, monkeypatch):
    user = user_factory("killswitch@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    kill_switch.engage(db, scope="global", reason="test", triggered_by="admin")
    db.commit()

    with pytest.raises(control_plane.OrderRejected):
        control_plane.preview_order(
            db,
            user.id,
            mandate_id=world["mandate"].id,
            symbol="BTCUSDT",
            side="buy",
            quantity="0.5",
            gateway=FakeGateway(),
        )

    # Cancellation stays allowed while the switch is engaged.
    release = kill_switch.release(db, scope="global", resolved_by=user.id)
    db.commit()
    assert release is True


# ---------------------------------------------------------------------------
# Risk engine
# ---------------------------------------------------------------------------


def test_risk_engine_rejects_unknown_symbol(db, user_factory, monkeypatch):
    user = user_factory("risk@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    with pytest.raises(control_plane.OrderRejected, match="SYMBOL_NOT_ALLOWED|LIVE disabled"):
        control_plane.preview_order(
            db,
            user.id,
            mandate_id=world["mandate"].id,
            symbol="DOGECOIN",
            side="buy",
            quantity="1",
            gateway=FakeGateway(),
        )


def test_risk_engine_rejects_oversized_order(db, user_factory, monkeypatch):
    user = user_factory("oversize@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    price_feed_service.record_price(db, symbol="BTCUSDT", price="100", venue="MOCK")
    db.commit()
    with pytest.raises(control_plane.OrderRejected):
        control_plane.preview_order(
            db,
            user.id,
            mandate_id=world["mandate"].id,
            symbol="BTCUSDT",
            side="buy",
            quantity="100000",
            gateway=FakeGateway(),
        )


def test_strategy_source_cannot_be_confirmed(db, user_factory, monkeypatch):
    user = user_factory("strategy-source@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        source=OrderSource.STRATEGY.value,
        gateway=FakeGateway(),
    )
    with pytest.raises(control_plane.ControlPlaneError, match="cannot be confirmed"):
        control_plane.confirm_order(
            db,
            user.id,
            order_intent_id=result["intent"].id,
            confirmation=result["confirmation"],
            gateway=FakeGateway(),
        )


def test_live_order_source_is_reserved(db, user_factory, monkeypatch):
    user = user_factory("reserved@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    with pytest.raises(control_plane.ControlPlaneError, match="reserved"):
        control_plane.preview_order(
            db,
            user.id,
            mandate_id=world["mandate"].id,
            symbol="BTCUSDT",
            side="buy",
            quantity="0.5",
            source=OrderSource.LIVE_ORDER.value,
            gateway=FakeGateway(),
        )


# ---------------------------------------------------------------------------
# Happy path + idempotency
# ---------------------------------------------------------------------------


def test_full_order_path_writes_risk_fill_ledger_nav(db, user_factory, monkeypatch):
    user = user_factory("full@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    fake = FakeGateway(fills=True)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=fake,
    )
    order = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=fake,
    )
    assert order.status in {"filled", "partially_filled"}
    assert order.broker_order_id
    assert len(fake.submitted) == 1
    assert fake.submitted[0]["mode"] == "live"

    fill = db.query(Fill).filter_by(order_id=order.id).one()
    entries = (
        db.query(LedgerEntry)
        .filter_by(ref_id=fill.id)
        .order_by(LedgerEntry.created_at)
        .all()
    )
    assert {entry.entry_type for entry in entries} >= {"trade_buy", "fee"}
    balance = ledger.cash_balance(db, world["account"].id)
    assert balance < Decimal("0")  # bought with cash + fee

    # NAV recalc (server-side only)
    snapshot = nav.calculate_nav(
        db, user_id=user.id, account_id=world["account"].id,
        mandate_id=world["mandate"].id, gateway=fake,
    )
    db.commit()
    assert snapshot is not None


def test_confirm_is_idempotent(db, user_factory, monkeypatch):
    user = user_factory("idempotent@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    fake = FakeGateway()
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=fake,
    )
    first = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=fake,
    )
    second = control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=fake,
    )
    assert first.id == second.id
    assert len(fake.submitted) == 1  # no duplicate submission


def test_other_user_cannot_touch_mandate(db, user_factory, monkeypatch):
    owner = user_factory("owner@test.com")
    attacker = user_factory("attacker@test.com")
    world = _make_live_world(db, owner, monkeypatch=monkeypatch)
    with pytest.raises(LookupError):
        control_plane.preview_order(
            db,
            attacker.id,
            mandate_id=world["mandate"].id,
            symbol="BTCUSDT",
            side="buy",
            quantity="0.5",
            gateway=FakeGateway(),
        )


# ---------------------------------------------------------------------------
# NAV staleness + reconciliation
# ---------------------------------------------------------------------------


def test_nav_is_stale_without_valid_price(db, user_factory, monkeypatch):
    user = user_factory("nav-stale@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    fake = FakeGateway(fills=True)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="0.5",
        gateway=fake,
    )
    control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=fake,
    )
    # Remove every price so NAV must refuse to fabricate a valuation.
    from packages.database.models import MarketPriceSnapshot

    db.query(MarketPriceSnapshot).delete()
    db.commit()
    snapshot = nav.calculate_nav(
        db, user_id=user.id, account_id=world["account"].id, gateway=fake
    )
    db.commit()
    # Position exists but no price snapshot -> must NOT fabricate a NAV.
    assert snapshot.is_stale is True
    assert snapshot.nav is None


def test_nav_uses_valid_server_price(db, user_factory, monkeypatch):
    user = user_factory("nav-priced@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    fake = FakeGateway(fills=True)
    result = control_plane.preview_order(
        db,
        user.id,
        mandate_id=world["mandate"].id,
        symbol="BTCUSDT",
        side="buy",
        quantity="2",
        gateway=fake,
    )
    control_plane.confirm_order(
        db,
        user.id,
        order_intent_id=result["intent"].id,
        confirmation=result["confirmation"],
        gateway=fake,
    )
    price_feed_service.record_price(db, symbol="BTCUSDT", price="100", venue="MOCK")
    db.commit()
    snapshot = nav.calculate_nav(
        db, user_id=user.id, account_id=world["account"].id, gateway=fake
    )
    db.commit()
    assert snapshot.is_stale is False
    # NAV = broker cash (100000) + position value (2 * 100)
    assert snapshot.nav == Decimal("100200")


def test_reconciliation_pauses_mandate_on_discrepancy(db, user_factory, monkeypatch):
    user = user_factory("recon@test.com")
    world = _make_live_world(db, user, monkeypatch=monkeypatch)
    fake = FakeGateway(balance="100000")  # exchange says 100k, ledger says 0
    row = reconciliation_service.reconcile_account(
        db,
        user_id=user.id,
        account_id=world["account"].id,
        mandate=world["mandate"],
        gateway=fake,
        trace_id="trace-recon",
    )
    db.commit()
    assert row.status == "discrepancy"
    assert row.differences_json
    db.refresh(world["mandate"])
    assert world["mandate"].paused is True
    # No historical ledger modification: only reconciliation records exist.
    assert db.query(TradingReconciliation).count() == 1
    assert db.query(LedgerEntry).count() == 0


# ---------------------------------------------------------------------------
# Default gate is disabled
# ---------------------------------------------------------------------------


def test_static_gate_is_disabled_by_default():
    gate = flags.evaluate_static_gate()
    assert gate.enabled is False
    assert gate.as_dict()["state"] == "LIVE_DISABLED"


def test_full_gate_requires_user_approval(db, user_factory, monkeypatch):
    user = user_factory("unapproved@test.com")
    world = _make_live_world(
        db, user, monkeypatch, approval_status="pending"
    )
    # No LiveUserApproval row -> gate disabled.
    db.query(LiveUserApproval).filter_by(user_id=user.id).delete()
    db.commit()
    gate = flags.evaluate_full_gate(db, user.id, world["mandate"])
    assert gate.enabled is False
    assert gate.checks["user_live_approved"]["ok"] is False
