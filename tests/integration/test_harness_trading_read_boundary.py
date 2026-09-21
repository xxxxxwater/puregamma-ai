"""Integration evidence for the *historical* trading observation API.

These tests intentionally do not authorize the Harness shared-token Remote, prove
exchange freshness, enable live trading, or replace venue reconciliation.
"""
from __future__ import annotations

from datetime import timedelta

from packages.database.models import (
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    TradingAccount,
    utcnow,
)
from tests.conftest import auth_headers


def _account(db, user, name):
    account = TradingAccount(
        user_id=user.id,
        name=name,
        venue="MOCK",
        account_type="PAPER",
        status="ACTIVE",
        permissions_json={
            "paper_order": True,
            "shadow_order": False,
            "live_order": False,
            "withdraw": False,
            "transfer": False,
        },
    )
    db.add(account)
    db.flush()
    return account


def _position(db, user, account, instrument):
    row = PositionSnapshot(
        user_id=user.id,
        account_id=account.id,
        instrument=instrument,
        quantity=1.25,
        side="LONG",
        average_price=100.0,
        mark_price=101.0,
        unrealized_pnl=1.25,
        realized_pnl=0.0,
        leverage=1.0,
    )
    db.add(row)
    db.flush()
    return row


def _order(db, user, account, client_id, *, state="FILLED", sequence=1):
    intent = OrderIntent(
        user_id=user.id,
        account_id=account.id,
        instrument="BTCUSDT",
        venue="MOCK",
        direction="BUY",
        quantity=0.01,
        notional=100.0,
        leverage=1.0,
        order_type="MARKET",
        reduce_only=False,
        execution_mode="PAPER",
        status="EXECUTED",
        approval_status="APPROVED",
        idempotency_key=f"harness-test-intent:{client_id}",
        expires_at=utcnow() + timedelta(hours=1),
    )
    db.add(intent)
    db.flush()
    row = OrderJournal(
        user_id=user.id,
        account_id=account.id,
        order_intent_id=intent.id,
        client_order_id=client_id,
        sequence=sequence,
        state=state,
        instrument="BTCUSDT",
        side="BUY",
        quantity=0.01,
        filled_quantity=0.01 if state == "FILLED" else 0.0,
        remaining_quantity=0.0 if state == "FILLED" else 0.01,
        reduce_only=False,
        idempotency_key=f"harness-test-journal:{client_id}:{sequence}",
    )
    db.add(row)
    db.flush()
    return row


def test_historical_positions_orders_are_real_user_scoped_and_not_claimed_fresh(
    api_client, db, max_user, normal_user
):
    owner = _account(db, max_user, "Owner paper")
    foreign = _account(db, normal_user, "Other paper")
    owned_position = _position(db, max_user, owner, "BTCUSDT")
    _position(db, normal_user, foreign, "ETHUSDT")
    owned_order = _order(db, max_user, owner, "owner-filled-1")
    _order(db, normal_user, foreign, "foreign-filled-1")
    db.commit()

    missing_auth = api_client.get(f"/trading/observations/{owner.id}")
    assert missing_auth.status_code in {401, 403}

    owner_response = api_client.get(
        f"/trading/observations/{owner.id}", headers=auth_headers(max_user)
    )
    assert owner_response.status_code == 200
    observation = owner_response.json()
    assert observation["account_id"] == owner.id
    assert observation["state"] == "stale"
    assert observation["source"] == "historical-trading-database"
    assert observation["complete"] is False
    assert observation["venue_verified"] is False
    assert observation["reason"]
    assert {row["id"] for row in observation["positions"]} == {owned_position.id}
    assert {row["id"] for row in observation["orders"]} == {owned_order.id}
    assert "ETHUSDT" not in str(observation)
    assert "foreign-filled-1" not in str(observation)

    forbidden = api_client.get(
        f"/trading/observations/{owner.id}", headers=auth_headers(normal_user)
    )
    assert forbidden.status_code == 404
    assert owned_position.id not in forbidden.text
    assert owned_order.id not in forbidden.text

    for route in ("positions", "orders"):
        foreign_selector = api_client.get(
            f"/trading/{route}",
            params={"account_id": owner.id},
            headers=auth_headers(normal_user),
        )
        assert foreign_selector.status_code == 404
        no_selector = api_client.get(
            f"/trading/{route}", headers=auth_headers(normal_user)
        )
        assert no_selector.status_code == 200
        assert owned_position.id not in no_selector.text
        assert owned_order.id not in no_selector.text


def test_terminal_order_is_queryable_by_client_id_beyond_bounded_list(
    api_client, db, max_user, normal_user
):
    account = _account(db, max_user, "History paper")
    other = _account(db, normal_user, "No history access")
    terminal = _order(db, max_user, account, "old-terminal-filled")
    # The legacy /orders list returns only the most recent 300 journal rows.
    # New rows must not render the terminal order permanently unqueryable.
    for number in range(305):
        _order(db, max_user, account, f"recent-{number:03d}", state="CREATED")
    db.commit()

    listed = api_client.get(
        "/trading/orders",
        params={"account_id": account.id},
        headers=auth_headers(max_user),
    )
    assert listed.status_code == 200
    assert len(listed.json()["orders"]) == 300
    assert terminal.id not in {item["id"] for item in listed.json()["orders"]}

    url = "/trading/orders/by-client-id/old-terminal-filled"
    response = api_client.get(
        url, params={"account_id": account.id}, headers=auth_headers(max_user)
    )
    assert response.status_code == 200
    assert response.json()["order"]["id"] == terminal.id
    assert response.json()["order"]["state"] == "FILLED"
    assert response.json()["venue_verified"] is False

    for user, selected_account in ((normal_user, account), (max_user, other)):
        blocked = api_client.get(
            url,
            params={"account_id": selected_account.id},
            headers=auth_headers(user),
        )
        assert blocked.status_code == 404
        assert terminal.id not in blocked.text

    not_found = api_client.get(
        "/trading/orders/by-client-id/no-such-client-id",
        params={"account_id": account.id},
        headers=auth_headers(max_user),
    )
    assert not_found.status_code == 404
