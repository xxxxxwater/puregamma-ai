from __future__ import annotations

from typing import Any

import httpx

from apps.api.config import get_settings


class RuntimeUnavailable(RuntimeError):
    pass


class NautilusRuntimeClient:
    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.nautilus_runtime_url).rstrip("/")
        self.secret = secret or settings.nautilus_runtime_secret
        self.timeout = timeout or settings.nautilus_runtime_timeout_seconds
        self.transport = transport

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", authenticated=False)

    def command(
        self, command_type: str, idempotency_key: str, payload: dict
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/commands/{command_type}",
            json={"idempotency_key": idempotency_key, "payload": payload},
        )

    def run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def market_quotes(
        self, symbols: list[str] | None = None, *, refresh: bool = False
    ) -> dict[str, Any]:
        params = [("symbols", symbol) for symbol in (symbols or [])]
        params.append(("refresh", "true" if refresh else "false"))
        return self._request("GET", "/market/quotes", params=params)

    def events(self, limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/events", params={"limit": limit})

    def account_state(self, account_id: str) -> dict[str, Any]:
        return self._request("GET", f"/accounts/{account_id}/state")

    def _request(
        self, method: str, path: str, *, authenticated: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if authenticated:
            headers["X-PG-Runtime-Secret"] = self.secret
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.request(
                    method, f"{self.base_url}{path}", headers=headers, **kwargs
                )
            if response.status_code >= 400:
                raise RuntimeUnavailable(
                    f"Runtime returned HTTP {response.status_code}: {response.text[:240]}"
                )
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
            raise RuntimeUnavailable(
                f"Nautilus runtime unavailable: {str(exc)[:240]}"
            ) from exc
