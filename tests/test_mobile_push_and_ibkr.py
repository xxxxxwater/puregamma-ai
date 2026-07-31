import hashlib
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apps.api.config import Settings
from apps.api.routers import portfolio
from apps.api.services import portfolio_service, push_device_service
from packages.notifications import apns
from packages.notifications.apns import APNsProvider
from packages.database.models import MobileOAuthSession, PushDevice
from tests.conftest import auth_headers


def test_register_push_device_encrypts_token_and_can_unregister(api_client, db, normal_user):
    token = "ab" * 32
    response = api_client.post(
        "/notifications/devices",
        headers=auth_headers(normal_user),
        json={"token": token, "environment": "sandbox", "locale": "zh-Hans", "timezone": "Asia/Shanghai"},
    )

    assert response.status_code == 200
    row = db.query(PushDevice).filter_by(user_id=normal_user.id).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(row.token_ciphertext)
    assert response.json()["device"]["locale"] == "zh"

    removed = api_client.post(
        "/notifications/devices/unregister",
        headers=auth_headers(normal_user),
        json={"token": token, "environment": "sandbox", "locale": "zh-Hans", "timezone": "Asia/Shanghai"},
    )
    assert removed.status_code == 200
    db.refresh(row)
    assert row.enabled is False


def test_free_user_can_select_ios_push_daily_brief(api_client, normal_user):
    response = api_client.put(
        "/notifications/preferences/daily-brief",
        headers=auth_headers(normal_user),
        json={"enabled": True, "channel": "push", "timezone": "Asia/Shanghai", "local_time": "09:30"},
    )

    assert response.status_code == 200
    assert response.json()["preference"]["channel"] == "push"


def test_apns_provider_sends_only_decrypted_server_token(db, normal_user, monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    settings = Settings(
        encryption_master_key="e" * 32,
        apns_enabled=True,
        apns_team_id="TEAMID",
        apns_key_id="KEYID",
        apns_bundle_id="ai.puregamma.ios",
        apns_private_key=private_pem,
    )
    monkeypatch.setattr(push_device_service, "get_settings", lambda: settings)
    monkeypatch.setattr(apns, "get_settings", lambda: settings)
    token = "cd" * 32
    row = push_device_service.register_device(db, normal_user, token=token, environment="sandbox", locale="en", timezone_name="UTC")
    requests = []

    class Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return {}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    monkeypatch.setattr(apns.httpx, "Client", Client)
    result = APNsProvider(db, [row]).send(normal_user.id, "research update", "push-1")

    assert result.ok is True
    assert requests[0][0].endswith(token)
    assert requests[0][1]["headers"]["apns-topic"] == "ai.puregamma.ios"
    assert token not in str(row.token_ciphertext)


def test_mobile_ibkr_callback_uses_one_time_app_exchange(api_client, db, pro_user, monkeypatch):
    settings = Settings(
        ibkr_oauth_authorize_url="https://ibkr.example/authorize",
        ibkr_oauth_token_url="https://ibkr.example/token",
        ibkr_client_id="client",
        ibkr_client_secret="server-secret",
        mobile_ibkr_oauth_redirect_uri="https://api.puregamma.ai/portfolio/ibkr/mobile/callback",
        mobile_portfolio_redirect_uris=("puregamma://oauth/ibkr",),
        portfolio_token_encryption_key="1XD45sytcUi1mO1Uf5k3CvROoL_mngkXXYMAM8mMSh0=",
    )
    monkeypatch.setattr(portfolio, "get_settings", lambda: settings)
    monkeypatch.setattr(portfolio_service, "get_settings", lambda: settings)
    start = api_client.post(
        "/portfolio/ibkr/mobile/start",
        headers=auth_headers(pro_user),
        json={"redirect_uri": "puregamma://oauth/ibkr"},
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]

    class TokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "server-token", "refresh_token": "server-refresh", "expires_in": 3600}

    monkeypatch.setattr(portfolio.requests, "post", lambda *args, **kwargs: TokenResponse())
    monkeypatch.setattr(portfolio, "sync_account", lambda db, user, account: None)
    callback = api_client.get(f"/portfolio/ibkr/mobile/callback?state={state}&code=provider-code", follow_redirects=False)
    assert callback.status_code == 302
    app_code = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]

    completed = api_client.post(
        "/portfolio/ibkr/mobile/complete",
        headers=auth_headers(pro_user),
        json={"code": app_code},
    )
    assert completed.status_code == 200
    replay = api_client.post(
        "/portfolio/ibkr/mobile/complete",
        headers=auth_headers(pro_user),
        json={"code": app_code},
    )
    assert replay.status_code == 400
    row = db.query(MobileOAuthSession).filter_by(provider="ibkr", state=state).one()
    assert row.consumed_at is not None
