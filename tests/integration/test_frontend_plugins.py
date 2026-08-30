from __future__ import annotations

"""GET /api/frontend/plugins manifest tests.

FastAPI decides who may load which builtin frontend plugin; the manifest
is read-only and never contains executable code or URLs.
"""
from tests.conftest import auth_headers


def test_frontend_plugins_requires_auth(api_client):
    response = api_client.get("/api/frontend/plugins")
    assert response.status_code == 401


def test_frontend_plugins_manifest_shape(api_client, max_user):
    response = api_client.get("/api/frontend/plugins", headers=auth_headers(max_user))
    assert response.status_code == 200, response.text
    plugins = response.json()["plugins"]
    assert len(plugins) == 6
    by_id = {entry["id"]: entry for entry in plugins}
    for entry in plugins:
        assert entry["entry"] == "builtin"
        assert entry["version"] == "1.0.0"
        assert isinstance(entry["enabled"], bool)
        assert isinstance(entry["routes"], list)
    # Read-only portfolio surface is available to a Max plan.
    assert by_id["puregamma.portfolio"]["enabled"] is True
    # Paper trading stays OFF until AUTO_TRADING_PAPER_ENABLED=true.
    assert by_id["puregamma.trading"]["enabled"] is False
    # LIVE trading console stays OFF until LIVE_TRADING_ENABLED=true.
    live = by_id["puregamma.live-trading"]
    assert live["enabled"] is False
    assert "trade:live" in live["permissions"]


def test_frontend_plugins_live_trading_flag_gate(api_client, max_user, monkeypatch):
    from apps.api.config import Settings
    from apps.api.routers import frontend

    monkeypatch.setattr(
        frontend,
        "get_settings",
        lambda: Settings(
            auto_trading_paper_enabled=True, live_trading_enabled=True
        ),
    )
    response = api_client.get("/api/frontend/plugins", headers=auth_headers(max_user))
    assert response.status_code == 200, response.text
    by_id = {entry["id"]: entry for entry in response.json()["plugins"]}
    assert by_id["puregamma.trading"]["enabled"] is True
    assert by_id["puregamma.live-trading"]["enabled"] is True


def test_frontend_plugins_trading_flag_gate(api_client, max_user, monkeypatch):
    from apps.api.config import Settings
    from apps.api.routers import frontend

    monkeypatch.setattr(frontend, "get_settings", lambda: Settings(auto_trading_paper_enabled=True))
    response = api_client.get("/api/frontend/plugins", headers=auth_headers(max_user))
    assert response.status_code == 200, response.text
    by_id = {entry["id"]: entry for entry in response.json()["plugins"]}
    assert by_id["puregamma.trading"]["enabled"] is True
