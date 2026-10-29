"""User-facing LIVE ledger and reconciliation reads.

Pins: only the owner sees an account's rows (another user's id is a 404, the
same answer as a nonexistent id), keyset pagination is stable and bounded,
money is a plain decimal string, and "no data" is never rendered as zero.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from packages.database.models import LedgerEntry, TradingAccount, TradingMandate, TradingReconciliation
from packages.live_trading import ledger
from tests.conftest import auth_headers
from tests.security.test_live_trading_foundation import _make_live_world


def _account(db, user, name="live") -> TradingAccount:
    row = TradingAccount(user_id=user.id, name=name, venue="MOCK", account_type="LIVE", base_currency="USD", status="ACTIVE")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _entry(db, user, account, *, key: str, amount: str, at: datetime | None = None, **extra) -> LedgerEntry:
    if at is None:
        row = ledger.post_entry(
            db, user_id=user.id, account_id=account.id, entry_type=extra.pop("entry_type", "cash_deposit"),
            amount=amount, idempotency_key=key, trace_id="t", **extra,
        )
    else:
        row = LedgerEntry(
            user_id=user.id, account_id=account.id, entry_type=extra.pop("entry_type", "cash_deposit"),
            amount=Decimal(amount), currency=extra.pop("currency", "USD"), idempotency_key=key, trace_id="t",
            created_at=at, **extra,
        )
        db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_another_users_account_is_a_404_identical_to_a_missing_one(api_client, db, user_factory):
    alice = user_factory("alice-ledger@test.com")
    bob = user_factory("bob-ledger@test.com")
    account = _account(db, alice)
    _entry(db, alice, account, key="a:1", amount="100")

    own = api_client.get(f"/api/trading/ledger?account_id={account.id}", headers=auth_headers(alice))
    assert own.status_code == 200
    assert [row["amount"] for row in own.json()["entries"]] == ["100.00000000"]

    foreign = api_client.get(f"/api/trading/ledger?account_id={account.id}", headers=auth_headers(bob))
    missing = api_client.get("/api/trading/ledger?account_id=does-not-exist", headers=auth_headers(bob))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"

    for path in ("/api/trading/reconciliation", "/api/trading/ledger"):
        response = api_client.get(f"{path}?account_id={account.id}", headers=auth_headers(bob))
        assert response.status_code == 404, path
        assert "100" not in response.text


def test_default_account_never_falls_back_to_another_user(api_client, db, user_factory):
    alice = user_factory("alice-default@test.com")
    bob = user_factory("bob-default@test.com")
    _entry(db, alice, _account(db, alice), key="a:default", amount="5")
    response = api_client.get("/api/trading/ledger", headers=auth_headers(bob))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"
    assert api_client.get("/api/trading/ledger", headers=auth_headers(alice)).status_code == 200


def test_another_users_mandate_filter_is_a_404(api_client, db, user_factory, monkeypatch):
    alice = user_factory("alice-mandate@test.com")
    bob = user_factory("bob-mandate@test.com")
    alice_world = _make_live_world(db, alice, monkeypatch)
    bob_account = _account(db, bob)
    response = api_client.get(
        f"/api/trading/ledger?account_id={bob_account.id}&mandate_id={alice_world['mandate'].id}",
        headers=auth_headers(bob),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRADING_MANDATE_NOT_FOUND"

    # A mandate of the right user but a different account is not a filter on
    # this account either.
    other = _account(db, alice, name="second")
    response = api_client.get(
        f"/api/trading/ledger?account_id={other.id}&mandate_id={alice_world['mandate'].id}",
        headers=auth_headers(alice),
    )
    assert response.status_code == 404


def test_a_cursor_carries_no_authority(api_client, db, user_factory):
    alice = user_factory("alice-cursor@test.com")
    bob = user_factory("bob-cursor@test.com")
    alice_account = _account(db, alice)
    bob_account = _account(db, bob)
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for index in range(3):
        _entry(db, alice, alice_account, key=f"a:{index}", amount="1", at=base + timedelta(minutes=index))
    _entry(db, bob, bob_account, key="b:0", amount="7", at=base - timedelta(days=1))

    first = api_client.get(f"/api/trading/ledger?account_id={alice_account.id}&limit=1", headers=auth_headers(alice)).json()
    assert first["next_cursor"]
    replay = api_client.get(
        f"/api/trading/ledger?account_id={bob_account.id}&cursor={first['next_cursor']}", headers=auth_headers(bob)
    ).json()
    assert [row["amount"] for row in replay["entries"]] == ["7.00000000"]
    assert all(row["account_id"] == bob_account.id for row in replay["entries"])


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _all_pages(api_client, user, account_id, limit):
    pages, cursor = [], None
    for _ in range(20):
        query = f"/api/trading/ledger?account_id={account_id}&limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        body = api_client.get(query, headers=auth_headers(user)).json()
        pages.append(body["entries"])
        cursor = body["next_cursor"]
        if not cursor:
            break
    return pages


def test_keyset_pages_are_stable_complete_and_bounded(api_client, db, user_factory):
    user = user_factory("pages@test.com")
    account = _account(db, user)
    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    # Three rows share one timestamp: the id tiebreak must still split them
    # across pages without loss or duplication.
    stamps = [base, base + timedelta(seconds=1), base + timedelta(seconds=1), base + timedelta(seconds=1), base + timedelta(seconds=2), base + timedelta(seconds=3), base + timedelta(seconds=4)]
    for index, stamp in enumerate(stamps):
        _entry(db, user, account, key=f"p:{index}", amount=str(index + 1), at=stamp)

    pages = _all_pages(api_client, user, account.id, limit=3)
    assert [len(page) for page in pages] == [3, 3, 1]
    ids = [row["id"] for page in pages for row in page]
    assert len(ids) == len(set(ids)) == 7
    ordered = [(row["created_at"], row["id"]) for page in pages for row in page]
    assert ordered == sorted(ordered, reverse=True)

    # Exactly one full page: no dangling cursor to an empty page.
    exact = api_client.get(f"/api/trading/ledger?account_id={account.id}&limit=7", headers=auth_headers(user)).json()
    assert len(exact["entries"]) == 7 and exact["next_cursor"] is None


def test_rows_appended_between_pages_do_not_shift_later_pages(api_client, db, user_factory):
    user = user_factory("append@test.com")
    account = _account(db, user)
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for index in range(4):
        _entry(db, user, account, key=f"s:{index}", amount="1", at=base + timedelta(minutes=index))
    first = api_client.get(f"/api/trading/ledger?account_id={account.id}&limit=2", headers=auth_headers(user)).json()
    _entry(db, user, account, key="s:new", amount="9", at=base + timedelta(hours=1))
    second = api_client.get(
        f"/api/trading/ledger?account_id={account.id}&limit=2&cursor={first['next_cursor']}", headers=auth_headers(user)
    ).json()
    seen = {row["id"] for row in first["entries"]} | {row["id"] for row in second["entries"]}
    assert len(seen) == 4
    assert "9.00000000" not in {row["amount"] for row in second["entries"]}
    assert second["next_cursor"] is None


@pytest.mark.parametrize("limit", [0, 201, -1])
def test_page_size_is_capped(api_client, db, user_factory, limit):
    user = user_factory(f"cap{limit}@test.com")
    account = _account(db, user)
    response = api_client.get(f"/api/trading/ledger?account_id={account.id}&limit={limit}", headers=auth_headers(user))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64-$$$",
        base64.urlsafe_b64encode(b"[1,2]").decode(),
        base64.urlsafe_b64encode(json.dumps({"v": 2, "t": "2026-10-01T00:00:00+00:00", "id": "x"}).encode()).decode(),
        base64.urlsafe_b64encode(json.dumps({"v": 1, "t": "yesterday", "id": "x"}).encode()).decode(),
    ],
)
def test_a_malformed_cursor_is_a_400_not_a_500(api_client, db, user_factory, cursor):
    user = user_factory("badcursor@test.com")
    account = _account(db, user)
    response = api_client.get(f"/api/trading/ledger?account_id={account.id}&cursor={cursor}", headers=auth_headers(user))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_CURSOR"


def test_entry_type_filter_is_validated(api_client, db, user_factory):
    user = user_factory("etype@test.com")
    account = _account(db, user)
    _entry(db, user, account, key="e:dep", amount="10")
    _entry(db, user, account, key="e:fee", amount="-1", entry_type="fee")
    fees = api_client.get(f"/api/trading/ledger?account_id={account.id}&entry_type=fee", headers=auth_headers(user)).json()
    assert [row["entry_type"] for row in fees["entries"]] == ["fee"]
    bad = api_client.get(f"/api/trading/ledger?account_id={account.id}&entry_type=withdraw_all", headers=auth_headers(user))
    assert bad.status_code == 400


# ---------------------------------------------------------------------------
# Decimal text, empty vs unavailable
# ---------------------------------------------------------------------------


def test_amounts_are_plain_decimal_strings(api_client, db, user_factory):
    user = user_factory("decimals@test.com")
    account = _account(db, user)
    _entry(db, user, account, key="d:1", amount="0.00000001")
    _entry(db, user, account, key="d:2", amount="-0.00000001")  # running balance back to 0E-8
    _entry(
        db, user, account, key="d:3", amount="-250.5", entry_type="trade_buy",
        symbol="btcusdt", quantity="2.5", price="100.2",
    )
    body = api_client.get(f"/api/trading/ledger?account_id={account.id}", headers=auth_headers(user)).json()
    numeric = [row[key] for row in body["entries"] for key in ("amount", "quantity", "price", "balance_after") if row[key] is not None]
    assert numeric and all(re.fullmatch(r"-?\d+\.\d{8}", value) for value in numeric), numeric
    by_key = {row["amount"]: row for row in body["entries"]}
    assert by_key["0.00000001"]["balance_after"] == "0.00000001"
    assert by_key["-0.00000001"]["balance_after"] == "0.00000000"
    trade = by_key["-250.50000000"]
    assert (trade["quantity"], trade["price"], trade["symbol"]) == ("2.50000000", "100.20000000", "BTCUSDT")
    deposit = by_key["0.00000001"]
    assert deposit["quantity"] is None and deposit["price"] is None
    for row in body["entries"]:
        assert isinstance(row["amount"], str)


def test_missing_running_balance_is_null_not_zero(api_client, db, user_factory):
    user = user_factory("nobalance@test.com")
    account = _account(db, user)
    _entry(db, user, account, key="n:1", amount="3", at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    row = api_client.get(f"/api/trading/ledger?account_id={account.id}", headers=auth_headers(user)).json()["entries"][0]
    assert row["balance_after"] is None


def test_empty_ledger_is_distinct_from_no_account(api_client, db, user_factory):
    user = user_factory("empty@test.com")
    none = api_client.get("/api/trading/reconciliation", headers=auth_headers(user))
    assert none.status_code == 404
    assert none.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"

    account = _account(db, user)
    page = api_client.get("/api/trading/ledger", headers=auth_headers(user)).json()
    assert page["entries"] == [] and page["next_cursor"] is None
    assert page["account"]["id"] == account.id

    view = api_client.get("/api/trading/reconciliation", headers=auth_headers(user)).json()
    assert view["ledger"] == {"entry_count": 0, "empty": True, "last_entry_at": None, "balances": [], "positions": []}
    # Never reconciled: the comparison is unavailable, not "no differences".
    assert view["latest"] is None and view["history"] == []


def test_reconciliation_view_sums_per_currency_and_normalizes_amounts(api_client, db, user_factory, monkeypatch):
    user = user_factory("recon@test.com")
    world = _make_live_world(db, user, monkeypatch)
    account = world["account"]
    _entry(db, user, account, key="r:dep", amount="1000")
    _entry(db, user, account, key="r:buy", amount="-200", entry_type="trade_buy", symbol="BTCUSDT", quantity="2", price="100")
    _entry(db, user, account, key="r:fee", amount="-0.0001", entry_type="fee", currency="BTC")
    db.add(
        TradingReconciliation(
            user_id=user.id, account_id=account.id, mandate_id=world["mandate"].id, status="discrepancy",
            exchange_balance_json={"cash": "790", "equity": None}, ledger_balance_json={"cash": "0E-8"},
            nav_json={"cash": "800", "nav": None},
            differences_json=[{"source": "exchange_vs_ledger", "exchange": "790", "ledger": "0E-8", "delta": "790"}],
            actions_json=["mandate_paused"], trace_id="recon-1",
        )
    )
    db.commit()
    view = api_client.get(f"/api/trading/reconciliation?account_id={account.id}", headers=auth_headers(user)).json()
    assert view["ledger"]["balances"] == [
        {"currency": "BTC", "amount": "-0.00010000"},
        {"currency": "USD", "amount": "800.00000000"},
    ]
    assert view["ledger"]["positions"] == [{"symbol": "BTCUSDT", "quantity": "2.00000000"}]
    latest = view["latest"]
    assert latest["status"] == "discrepancy"
    assert latest["ledger_balance"] == {"cash": "0.00000000"}
    assert latest["exchange_balance"] == {"cash": "790", "equity": None}
    assert latest["differences"][0]["ledger"] == "0.00000000"
    assert latest["reviewed"] is None
    assert view["history"][0]["difference_count"] == 1


def test_mandate_filter_returns_only_that_mandates_rows(api_client, db, user_factory, monkeypatch):
    user = user_factory("mfilter@test.com")
    world = _make_live_world(db, user, monkeypatch)
    account, mandate = world["account"], world["mandate"]
    _entry(db, user, account, key="m:dep", amount="10")
    _entry(db, user, account, key="m:buy", amount="-1", mandate_id=mandate.id, entry_type="trade_buy", symbol="BTCUSDT", quantity="1", price="1")
    rows = api_client.get(
        f"/api/trading/ledger?account_id={account.id}&mandate_id={mandate.id}", headers=auth_headers(user)
    ).json()["entries"]
    assert [row["entry_type"] for row in rows] == ["trade_buy"]
    assert db.query(TradingMandate).count() == 1
