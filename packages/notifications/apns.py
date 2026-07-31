from __future__ import annotations

import base64
import json
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.services.push_device_service import decrypt_device_token
from packages.database.models import PushDevice
from packages.notifications.base import NotificationResult


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class APNsProvider:
    channel = "push"

    def __init__(self, db: Session, devices: list[PushDevice]):
        self.db = db
        self.devices = devices
        self.settings = get_settings()

    def _provider_token(self) -> str:
        header = _b64(json.dumps({"alg": "ES256", "kid": self.settings.apns_key_id}, separators=(",", ":")).encode())
        payload = _b64(json.dumps({"iss": self.settings.apns_team_id, "iat": int(time.time())}, separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}".encode()
        key = serialization.load_pem_private_key(self.settings.apns_private_key.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise RuntimeError("APNS_PRIVATE_KEY is not an EC private key")
        der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return f"{header}.{payload}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        if not self.settings.apns_enabled or not self.devices:
            return NotificationResult(False, self.channel, {"status": "provider_unavailable" if not self.settings.apns_enabled else "no_active_devices"})
        authorization = self._provider_token()
        results: list[dict] = []
        successful = 0
        payload = {"aps": {"alert": {"title": "PureGamma", "body": message[:3000]}, "sound": "default", "thread-id": "puregamma-research"}}
        with httpx.Client(http2=True, timeout=10.0) as client:
            for device in self.devices:
                token = decrypt_device_token(device)
                host = "https://api.sandbox.push.apple.com" if device.environment == "sandbox" else "https://api.push.apple.com"
                response = client.post(
                    f"{host}/3/device/{token}",
                    headers={
                        "authorization": f"bearer {authorization}",
                        "apns-topic": self.settings.apns_bundle_id,
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                    json=payload,
                )
                reason = ""
                if response.content:
                    try:
                        reason = str(response.json().get("reason") or "")
                    except ValueError:
                        reason = response.text[:120]
                if response.status_code == 200:
                    successful += 1
                elif response.status_code == 410 or reason in {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}:
                    device.enabled = False
                results.append({"device_id": device.id, "status": response.status_code, "reason": reason})
        self.db.commit()
        return NotificationResult(successful > 0, self.channel, {"status": "sent" if successful else "failed", "sent": successful, "devices": results})
