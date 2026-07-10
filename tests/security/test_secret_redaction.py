from __future__ import annotations

import pytest

from tests.conftest import auth_headers


def test_auth_me_does_not_return_bearer_token(api_client, demo_user):
    response = api_client.get("/me", headers=auth_headers(demo_user))

    assert response.status_code == 200
    assert "access_token" not in response.json()["user"]


@pytest.mark.contract
def test_plaid_access_token_not_returned_contract():
    pytest.xfail("No Plaid API schemas exist yet. Expected: access_token/encrypted_access_token never appear in API responses.")


@pytest.mark.contract
def test_exchange_api_key_not_returned_contract():
    pytest.xfail("No exchange API schemas exist yet. Expected: api_secret/passphrase never appear in API responses.")
