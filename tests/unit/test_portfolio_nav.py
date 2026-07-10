from __future__ import annotations

import pytest


@pytest.mark.contract
def test_plaid_only_nav_contract():
    pytest.xfail("No portfolio NAV service exists yet. Expected: Plaid holdings only compute NAV from fixed test prices.")


@pytest.mark.contract
def test_cex_only_nav_contract():
    pytest.xfail("No portfolio NAV service exists yet. Expected: exchange balances only compute NAV from fixed test prices.")


@pytest.mark.contract
def test_wallet_only_nav_contract():
    pytest.xfail("No portfolio NAV service exists yet. Expected: on-chain wallet balances compute NAV including stablecoins.")


@pytest.mark.contract
def test_mixed_sources_do_not_double_count_duplicate_assets_contract():
    pytest.xfail("No portfolio NAV service exists yet. Expected: same asset from multiple sources is intentionally aggregated by source without duplicate record replay.")


@pytest.mark.contract
def test_sync_failure_does_not_overwrite_last_valid_snapshot_contract():
    pytest.xfail("No persisted portfolio snapshot model exists yet. Expected: failed source sync preserves previous valid NAV.")
