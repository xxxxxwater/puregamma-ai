from __future__ import annotations

import pytest


@pytest.mark.contract
def test_add_wallet_rejects_invalid_address_contract():
    pytest.xfail("No wallet service/router exists yet. Expected: invalid addresses rejected before persistence.")


@pytest.mark.contract
def test_sync_wallet_balances_contract():
    pytest.xfail("No wallet balance sync exists yet. Expected: on-chain balances normalize with stablecoin pricing.")


@pytest.mark.contract
def test_wallet_owner_scope_contract():
    pytest.xfail("No wallet model exists yet. Expected: user A cannot read or sync user B wallets.")
