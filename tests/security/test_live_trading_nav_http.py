"""HTTP contract of the server-computed NAV endpoints.

A user without a LIVE account gets an explicit "not found" the console renders
as unavailable - never a 500 that reads as an outage and never a zero NAV. An
account id belonging to someone else is indistinguishable from a missing one.
Money crosses the wire as decimal strings.
"""
from __future__ import annotations

import re

import pytest

from packages.database.models import TradingAccount
from tests.conftest import auth_headers

ENDPOINTS = ["/api/portfolio/nav", "/api/portfolio/nav/history", "/api/portfolio/positions"]
DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")


@pytest.mark.parametrize("path", ENDPOINTS)
def test_no_trading_account_is_an_explicit_not_found(api_client, normal_user, path):
    response = api_client.get(path, headers=auth_headers(normal_user))
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_another_users_account_id_is_not_found(api_client, db, normal_user, max_user, path):
    foreign = TradingAccount(user_id=max_user.id, name="theirs", venue="MOCK", account_type="LIVE", status="ACTIVE")
    db.add(foreign)
    db.commit()
    response = api_client.get(f"{path}?account_id={foreign.id}", headers=auth_headers(normal_user))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRADING_ACCOUNT_NOT_FOUND"


def test_nav_for_an_owned_account_is_decimal_strings_with_a_staleness_flag(api_client, db, normal_user):
    account = TradingAccount(user_id=normal_user.id, name="mine", venue="MOCK", account_type="LIVE", status="ACTIVE")
    db.add(account)
    db.commit()
    response = api_client.get("/api/portfolio/nav", headers=auth_headers(normal_user))
    assert response.status_code == 200, response.text
    nav = response.json()["nav"]
    assert nav["account_id"] == account.id
    assert isinstance(nav["is_stale"], bool)
    assert nav["nav"] is None or DECIMAL.match(nav["nav"])
    for field in ("cash", "gross_exposure", "net_exposure", "realized_pnl", "unrealized_pnl"):
        assert isinstance(nav[field], str) and DECIMAL.match(nav[field]), (field, nav[field])
    assert nav["calculated_at"]
    history = api_client.get("/api/portfolio/nav/history", headers=auth_headers(normal_user))
    assert history.status_code == 200
    assert all(row["account_id"] == account.id for row in history.json()["history"])


def test_decimal_text_never_uses_exponent_notation():
    from decimal import Decimal

    from packages.live_trading.decimal_text import decimal_text

    assert str(Decimal("0E-8")) == "0E-8"  # the bug: what str() put on the wire
    assert decimal_text(Decimal("0E-8")) == "0.00000000"
    assert decimal_text(Decimal("1234.50000000")) == "1234.50000000"
    assert decimal_text(Decimal("-0.00000001")) == "-0.00000001"
    assert decimal_text(Decimal("1E+3")) == "1000"
    assert decimal_text(None) is None
