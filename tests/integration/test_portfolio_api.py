from __future__ import annotations

import pytest


@pytest.mark.contract
def test_portfolio_snapshot_api_contract():
    pytest.xfail("No backend portfolio API route exists yet. Expected: authenticated user receives only their latest NAV snapshot.")


@pytest.mark.contract
def test_user_a_cannot_read_user_b_portfolio_contract():
    pytest.xfail("No backend portfolio API route/model exists yet. Expected: cross-tenant portfolio access returns 404/403.")


@pytest.mark.contract
def test_partial_data_warning_contract():
    pytest.xfail("No backend portfolio API route/model exists yet. Expected: partial/stale source warnings included with NAV.")
