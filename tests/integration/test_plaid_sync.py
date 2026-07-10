from __future__ import annotations

import pytest


@pytest.mark.contract
def test_create_link_token_mock_contract():
    pytest.xfail("No Plaid service/router exists yet. Expected: create link token returns mock token without real credentials.")


@pytest.mark.contract
def test_exchange_public_token_encrypts_access_token_contract():
    pytest.xfail("No Plaid token exchange exists yet. Expected: access token stored encrypted and never returned by API.")


@pytest.mark.contract
def test_plaid_holdings_and_transactions_normalize_contract():
    pytest.xfail("No Plaid normalization module exists yet. Expected: holdings and investment transactions normalize to portfolio source rows.")


@pytest.mark.contract
def test_disconnect_plaid_deletes_encrypted_token_contract():
    pytest.xfail("No Plaid connection model exists yet. Expected: disconnect deletes encrypted token and marks source disconnected.")
