from __future__ import annotations

import pytest


@pytest.mark.contract
def test_portfolio_nav_job_contract():
    pytest.xfail("No portfolio NAV worker task exists yet. Expected: scheduled NAV job writes snapshots and preserves previous valid snapshot on partial source failure.")
