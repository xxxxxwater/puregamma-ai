from urllib.parse import parse_qs, urlparse

from apps.api.config import Settings
from apps.api.routers import mobile_auth
from packages.database.models import MobileOAuthSession


def mobile_settings() -> Settings:
    return Settings(
        google_client_id="google-client",
        google_client_secret="google-secret",
        mobile_google_oauth_redirect_uri="https://api.example.com/auth/mobile/google/callback",
        mobile_oauth_redirect_uris=("puregamma://oauth/callback",),
    )


def test_mobile_google_pkce_exchange_is_single_use(api_client, db, monkeypatch):
    monkeypatch.setattr(mobile_auth, "get_settings", mobile_settings)
    monkeypatch.setattr(mobile_auth, "_exchange_code_for_token", lambda *args: {"id_token": "id-token"})
    holder = {"nonce": ""}
    monkeypatch.setattr(mobile_auth, "_verify_google_id_token", lambda token, client_id: {"sub": "ios-google-sub", "email": "ios@example.com", "name": "iOS User", "email_verified": True, "nonce": holder["nonce"]})
    verifier = "v" * 64
    nonce = "n" * 40
    client_state = "s" * 40
    start = api_client.post("/auth/mobile/google/start", json={"redirect_uri": "puregamma://oauth/callback", "code_challenge": mobile_auth._challenge(verifier), "client_state": client_state, "nonce": nonce})
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["auth_url"]).query)["state"][0]
    holder["nonce"] = db.query(MobileOAuthSession).filter_by(state=state).one().provider_nonce
    callback = api_client.get(f"/auth/mobile/google/callback?code=google-code&state={state}", follow_redirects=False)
    assert callback.status_code == 302
    query = parse_qs(urlparse(callback.headers["location"]).query)
    assert query["state"][0] == client_state
    exchange = api_client.post("/auth/mobile/google/exchange", json={"code": query["code"][0], "code_verifier": verifier, "nonce": nonce})
    assert exchange.status_code == 200
    assert exchange.json()["token_type"] == "bearer"
    token = exchange.json()["access_token"]
    assert api_client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert api_client.post("/auth/mobile/google/exchange", json={"code": query["code"][0], "code_verifier": verifier, "nonce": nonce}).status_code == 400


def test_mobile_google_rejects_unlisted_redirect(api_client, monkeypatch):
    monkeypatch.setattr(mobile_auth, "get_settings", mobile_settings)
    response = api_client.post("/auth/mobile/google/start", json={"redirect_uri": "attacker://callback", "code_challenge": "a" * 43, "client_state": "s" * 40, "nonce": "n" * 40})
    assert response.status_code == 400


def test_mobile_google_cancel_returns_to_allowlisted_app(api_client, monkeypatch):
    monkeypatch.setattr(mobile_auth, "get_settings", mobile_settings)
    start = api_client.post("/auth/mobile/google/start", json={"redirect_uri": "puregamma://oauth/callback", "code_challenge": "a" * 43, "client_state": "s" * 40, "nonce": "n" * 40})
    state = parse_qs(urlparse(start.json()["auth_url"]).query)["state"][0]
    callback = api_client.get(f"/auth/mobile/google/callback?error=access_denied&state={state}", follow_redirects=False)
    assert callback.status_code == 302
    query = parse_qs(urlparse(callback.headers["location"]).query)
    assert query == {"error": ["oauth_canceled"], "state": ["s" * 40]}
