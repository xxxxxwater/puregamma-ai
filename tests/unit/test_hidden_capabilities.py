import pytest
from fastapi import HTTPException

from apps.api.routers.internal import _capability, _guard


def test_hidden_capability_is_not_publicly_healthy_by_default():
    row = _capability("risk_copilot", enabled=False)
    assert row["enabled"] is False
    assert row["status"] == "DISABLED"
    assert row["production_allowed"] is False


def test_hidden_capability_contract_is_explicitly_not_implemented():
    row = _capability("risk_copilot", enabled=True)
    assert row["status"] == "NOT_IMPLEMENTED"
    assert row["error_code"] == "CAPABILITY_NOT_IMPLEMENTED"


def test_disabled_route_is_fail_closed():
    with pytest.raises(HTTPException) as error:
        _guard(False, "trading_mcp")
    assert error.value.status_code == 404
