"""Wallet sign-in (SIWE / EIP-4361) tests.

Covers: nonce issuance, account auto-creation on first verify, replay
(single-use nonce), wrong-signer rejection, bad address validation, and
login of a returning wallet user.
"""

from __future__ import annotations

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from apps.api.routers import wallet_auth
from packages.database.models import User, UserIdentity


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def getdel(self, key):
        return self.store.pop(key, None)

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def expire(self, key, window):
        return True


@pytest.fixture()
def fake_redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(wallet_auth, "_redis", lambda: client)
    return client


def _sign(message: str, key: str) -> str:
    return Account.sign_message(encode_defunct(text=message), private_key=key).signature.hex()


def test_wallet_nonce_and_verify_creates_user(api_client, db, fake_redis):
    account = Account.create()
    nonce_resp = api_client.post("/auth/wallet/nonce", json={"address": account.address, "chain_id": 1})
    assert nonce_resp.status_code == 200
    message = nonce_resp.json()["message"]
    assert account.address in message
    assert "Nonce:" in message

    verify_resp = api_client.post(
        "/auth/wallet/verify",
        json={"address": account.address, "signature": _sign(message, account.key.hex()), "wallet": "metamask"},
    )
    assert verify_resp.status_code == 200
    body = verify_resp.json()["user"]
    assert body["role"] == "user"
    assert "set-cookie" in {k.lower() for k in verify_resp.headers.keys()}

    user = db.query(User).filter(User.email.like("%@wallet.puregamma.local")).one()
    identity = db.query(UserIdentity).filter_by(provider="evm_wallet", provider_subject=account.address.lower()).one()
    assert identity.user_id == user.id
    assert user.auth_provider == "wallet"


def test_wallet_verify_rejects_replayed_nonce(api_client, db, fake_redis):
    account = Account.create()
    message = api_client.post("/auth/wallet/nonce", json={"address": account.address}).json()["message"]
    signature = _sign(message, account.key.hex())
    first = api_client.post("/auth/wallet/verify", json={"address": account.address, "signature": signature, "wallet": "zerion"})
    assert first.status_code == 200
    replay = api_client.post("/auth/wallet/verify", json={"address": account.address, "signature": signature, "wallet": "zerion"})
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "WALLET_NONCE_EXPIRED"


def test_wallet_verify_rejects_wrong_signer(api_client, db, fake_redis):
    claimed = Account.create()
    attacker = Account.create()
    message = api_client.post("/auth/wallet/nonce", json={"address": claimed.address}).json()["message"]
    # The attacker signs the victim's message with their own key.
    signature = _sign(message, attacker.key.hex())
    response = api_client.post("/auth/wallet/verify", json={"address": claimed.address, "signature": signature, "wallet": "metamask"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "WALLET_SIGNATURE_MISMATCH"
    assert db.query(UserIdentity).filter_by(provider="evm_wallet").count() == 0


def test_wallet_nonce_rejects_bad_address(api_client, db, fake_redis):
    # Wrong length is rejected by schema validation...
    short = api_client.post("/auth/wallet/nonce", json={"address": "0x1234"})
    assert short.status_code in (400, 422)
    # ...and a 42-char string that is not hex is rejected by the regex.
    invalid = api_client.post("/auth/wallet/nonce", json={"address": "0xZZZZ567890abcdef1234567890abcdef12345678"})
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "INVALID_WALLET_ADDRESS"


def test_wallet_verify_rejects_unsupported_wallet(api_client, db, fake_redis):
    account = Account.create()
    api_client.post("/auth/wallet/nonce", json={"address": account.address})
    response = api_client.post("/auth/wallet/verify", json={"address": account.address, "signature": "0xdeadbeef", "wallet": "evil"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_WALLET"


def test_returning_wallet_user_logs_into_same_account(api_client, db, fake_redis):
    account = Account.create()
    for _ in range(2):
        message = api_client.post("/auth/wallet/nonce", json={"address": account.address}).json()["message"]
        response = api_client.post(
            "/auth/wallet/verify",
            json={"address": account.address, "signature": _sign(message, account.key.hex()), "wallet": "injected"},
        )
        assert response.status_code == 200
    assert db.query(UserIdentity).filter_by(provider="evm_wallet", provider_subject=account.address.lower()).count() == 1
