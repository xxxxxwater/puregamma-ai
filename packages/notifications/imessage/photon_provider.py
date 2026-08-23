from __future__ import annotations

"""Photon-hosted iMessage provider.

Speaks the Photon "Advanced iMessage HTTP Proxy" contract so PureGamma can
deliver iMessage through Photon (https://photon.codes) instead of the
self-hosted macOS relay. Photon is a SWITCHABLE provider selected with
IMESSAGE_PROVIDER=photon; it is never an automatic fallback for the Mac
relay, and the Mac relay keeps working unchanged when
IMESSAGE_PROVIDER=macos_relay.

Contract implemented here:

- Text: POST {PHOTON_HTTP_PROXY_URL}/send with JSON {"to": ..., "text": ...}.
- Media: POST {PHOTON_HTTP_PROXY_URL}/send/file as multipart/form-data with
  "to", "file" and (for audio) "audio=true".
- Proxy bearer token: Base64 of "{PHOTON_SERVER_URL}|{PHOTON_API_KEY}".
  The token, message bodies, media bytes and phone numbers are never logged
  and are stripped from the persisted provider_response.
- Idempotency: every PureGamma idempotency key is forwarded as the
  "Idempotency-Key" request header. KNOWN LIMITATION: some Photon proxy
  versions do not honor that header; the local NotificationDelivery
  idempotency layer in the dispatcher remains the trusted deduplication
  boundary either way.

Failure mapping (see _map_error):

- 2xx with {"ok": true} -> success.
- 4xx VALIDATION_ERROR / invalid-recipient codes -> permanent failure
  (status "invalid_recipient").
- 5xx, timeouts, network errors, UPSTREAM_ERROR -> retryable
  (status "failed_retryable") with short exponential backoff.

Missing configuration (PHOTON_API_KEY, PHOTON_HTTP_PROXY_URL or
PHOTON_SERVER_URL) returns NotificationResult(False, ...,
{"error": "missing_photon_configuration"}); it never raises an unhandled
exception.
"""

import base64
import json
import time
import urllib.error
import urllib.request
import uuid

from apps.api.config import Settings, get_settings
from packages.notifications.base import NotificationResult
from packages.notifications.imessage.base import IMessageProvider

# Statuses the dispatcher already treats as permanent iMessage failures.
PERMANENT_RECIPIENT_CODES = {"VALIDATION_ERROR", "INVALID_RECIPIENT", "INVALID_TO", "RECIPIENT_NOT_FOUND"}

# Only these response fields may be persisted in NotificationDelivery.provider_response.
# Everything else (recipients, message bodies, media metadata, tokens) is dropped.
SAFE_RESPONSE_KEYS = ("ok", "status", "id", "message_id", "mode")


def _safe_response(payload: dict) -> dict:
    """Whitelist the proxy response so no secret or message content persists."""
    clean: dict = {}
    for key in SAFE_RESPONSE_KEYS:
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            clean[key] = value
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code:
            clean["error"] = {"code": code}
    elif isinstance(error, str) and error:
        clean["error"] = error
    return clean


class PhotonIMessageProvider(IMessageProvider):
    channel = "imessage"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    # -- configuration -------------------------------------------------

    def _missing_configuration(self) -> list[str]:
        return [
            name
            for name, value in (
                ("PHOTON_API_KEY", self.settings.photon_api_key),
                ("PHOTON_HTTP_PROXY_URL", self.settings.photon_http_proxy_url),
                ("PHOTON_SERVER_URL", self.settings.photon_server_url),
            )
            if not value
        ]

    def _authorization(self) -> str:
        # Per the Photon proxy docs: base64("{server_url}|{api_key}").
        token = f"{self.settings.photon_server_url}|{self.settings.photon_api_key}"
        return base64.b64encode(token.encode()).decode()

    def _proxy_url(self, path: str) -> str:
        return f"{self.settings.photon_http_proxy_url.rstrip('/')}/{path.lstrip('/')}"

    # -- result mapping ------------------------------------------------

    def _map_error(self, payload: dict) -> NotificationResult:
        error = payload.get("error")
        code = ""
        if isinstance(error, dict):
            code = str(error.get("code") or "")
        elif isinstance(error, str):
            code = error
        code = (code or str(payload.get("code") or payload.get("status") or "")).upper()
        if code in PERMANENT_RECIPIENT_CODES or "RECIPIENT" in code or code == "VALIDATION_ERROR":
            return NotificationResult(False, self.channel, {"status": "invalid_recipient", "error": code})
        return NotificationResult(False, self.channel, {"status": "failed_retryable", "error": code or "upstream_error"})

    def _map_response(self, status: int, payload: dict) -> NotificationResult:
        if 200 <= status < 300 and payload.get("ok") is True:
            clean = _safe_response(payload)
            return NotificationResult(True, self.channel, clean or {"ok": True, "status": "sent"})
        return self._map_error(payload)

    # -- transport ------------------------------------------------------

    def _request(
        self,
        url: str,
        *,
        data: bytes,
        content_type: str,
        idempotency_key: str,
        timeout: float,
        attempts: int = 3,
    ) -> NotificationResult:
        """POST with bearer auth + Idempotency-Key. Network/5xx failures retry
        with short exponential backoff; 4xx permanent failures return at once."""
        headers = {
            "Authorization": f"Bearer {self._authorization()}",
            "Content-Type": content_type,
            "Idempotency-Key": idempotency_key,
        }
        last_error: str | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    try:
                        payload = json.loads(response.read().decode() or "{}")
                    except (ValueError, UnicodeDecodeError):
                        payload = {}
                    return self._map_response(response.status, payload)
            except urllib.error.HTTPError as exc:
                try:
                    payload = json.loads(exc.read().decode() or "{}")
                except (ValueError, UnicodeDecodeError, AttributeError):
                    payload = {}
                if exc.code is not None and 400 <= exc.code < 500:
                    return self._map_response(exc.code, payload)
                last_error = f"HTTP_{exc.code}"
            except (urllib.error.URLError, TimeoutError, OSError, ConnectionError) as exc:
                last_error = exc.__class__.__name__
            if attempt < attempts - 1:
                time.sleep(0.1 * (2**attempt))
        return NotificationResult(False, self.channel, {"status": "failed_retryable", "error": last_error or "photon_failed"})

    # -- IMessageProvider -----------------------------------------------

    def send_message(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        missing = self._missing_configuration()
        if missing:
            return NotificationResult(
                False,
                self.channel,
                {"error": "missing_photon_configuration", "missing": missing},
            )
        payload = json.dumps({"to": recipient, "text": message}, separators=(",", ":")).encode()
        return self._request(
            self._proxy_url("/send"),
            data=payload,
            content_type="application/json",
            idempotency_key=idempotency_key,
            timeout=self.settings.photon_request_timeout_seconds,
        )

    def send_media(
        self,
        recipient: str,
        file_bytes: bytes,
        *,
        filename: str,
        kind: str,
        idempotency_key: str,
    ) -> NotificationResult:
        """Send a media attachment through the proxy multipart endpoint.
        kind="audio" adds audio=true so Photon delivers a voice bubble."""
        missing = self._missing_configuration()
        if missing:
            return NotificationResult(
                False,
                self.channel,
                {"error": "missing_photon_configuration", "missing": missing},
            )
        boundary = f"----puregamma-photon-{uuid.uuid4().hex}"
        parts: list[bytes] = []

        def field(name: str, value: str) -> None:
            header = (
                "--" + boundary + "\r\n"
                + 'Content-Disposition: form-data; name="' + name + '"\r\n\r\n'
                + value + "\r\n"
            )
            parts.append(header.encode())

        field("to", recipient)
        file_header = (
            "--" + boundary + "\r\n"
            + 'Content-Disposition: form-data; name="file"; filename="' + filename + '"\r\n'
            + "Content-Type: application/octet-stream\r\n\r\n"
        )
        parts.append(file_header.encode())
        parts.append(file_bytes)
        parts.append(b"\r\n")
        if kind == "audio":
            field("audio", "true")
        parts.append(("--" + boundary + "--\r\n").encode())
        body = b"".join(parts)
        return self._request(
            self._proxy_url("/send/file"),
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            idempotency_key=idempotency_key,
            timeout=max(self.settings.photon_request_timeout_seconds * 3, 30),
        )
