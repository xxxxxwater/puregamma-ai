from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import RLock

import httpx


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_asset(value: str) -> str:
    symbol = value.upper().split(".", 1)[0].replace("-PERP", "")
    for quote in ("USDT", "USDC", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol


class PublicMarketProvider:
    provider_name = "public"

    def __init__(self, timeout: float, failure_threshold: int, recovery_seconds: int):
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.failures = 0
        self.last_success_at: str | None = None
        self.last_error: str | None = None
        self.open_until = 0.0

    def fetch_quotes(self, assets: list[str]) -> list[dict]:
        raise NotImplementedError

    def _before_request(self) -> None:
        if time.monotonic() < self.open_until:
            raise RuntimeError(f"{self.provider_name} circuit is open")

    def _success(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.last_error = None
        self.last_success_at = utc_iso()

    def _failure(self, exc: Exception) -> None:
        self.failures += 1
        self.last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
        if self.failures >= self.failure_threshold:
            self.open_until = time.monotonic() + self.recovery_seconds

    def status(self) -> dict:
        circuit_open = time.monotonic() < self.open_until
        return {
            "provider": self.provider_name,
            "status": "DEGRADED"
            if self.failures
            else "HEALTHY"
            if self.last_success_at
            else "IDLE",
            "lastSuccessAt": self.last_success_at,
            "failures": self.failures,
            "lastError": self.last_error,
            "circuitOpen": circuit_open,
            "liveOrders": False,
        }


class HyperliquidPublicMarketProvider(PublicMarketProvider):
    provider_name = "hyperliquid_public"

    def __init__(self, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")

    def fetch_quotes(self, assets: list[str]) -> list[dict]:
        self._before_request()
        try:
            response = httpx.post(
                f"{self.base_url}/info",
                json={"type": "allMids"},
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "PureGamma-PaperRuntime/1.0",
                },
            )
            response.raise_for_status()
            mids = response.json()
            if not isinstance(mids, dict):
                raise ValueError("Hyperliquid allMids response is not an object")
            now = utc_iso()
            quotes = []
            for asset in assets:
                raw = mids.get(asset)
                if raw is None:
                    continue
                price = float(raw)
                if price <= 0:
                    continue
                quotes.append(
                    {
                        "asset": asset,
                        "symbol": f"{asset}USDT",
                        "price": price,
                        "provider": self.provider_name,
                        "timestamp": now,
                        "stale": False,
                    }
                )
            self._success()
            return quotes
        except Exception as exc:
            self._failure(exc)
            raise


class CoinbasePublicMarketProvider(PublicMarketProvider):
    provider_name = "coinbase_public"

    def __init__(self, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")

    def fetch_quotes(self, assets: list[str]) -> list[dict]:
        self._before_request()
        quotes = []
        errors = []
        now = utc_iso()
        for asset in assets:
            try:
                response = httpx.get(
                    f"{self.base_url}/products/{asset}-USD/ticker",
                    timeout=self.timeout,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "PureGamma-PaperRuntime/1.0",
                    },
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                price = float(response.json()["price"])
                if price > 0:
                    quotes.append(
                        {
                            "asset": asset,
                            "symbol": f"{asset}USD",
                            "price": price,
                            "provider": self.provider_name,
                            "timestamp": now,
                            "stale": False,
                        }
                    )
            except Exception as exc:
                errors.append(exc)
        if quotes:
            self._success()
            return quotes
        error = (
            errors[0]
            if errors
            else RuntimeError("Coinbase returned no supported assets")
        )
        self._failure(error)
        raise error


class PublicMarketDataRouter:
    def __init__(
        self, providers: list[PublicMarketProvider], cache_ttl_seconds: int = 5
    ):
        self.providers = providers
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = RLock()

    def fetch(self, symbols: list[str], force: bool = False) -> dict:
        assets = list(
            dict.fromkeys(normalize_asset(symbol) for symbol in symbols if symbol)
        )
        now = time.monotonic()
        with self._lock:
            fresh = {
                asset: value
                for asset, (cached_at, value) in self._cache.items()
                if asset in assets and now - cached_at <= self.cache_ttl_seconds
            }
        missing = [asset for asset in assets if force or asset not in fresh]
        errors = []
        for provider in self.providers:
            if not missing:
                break
            try:
                values = provider.fetch_quotes(missing)
                with self._lock:
                    for value in values:
                        self._cache[value["asset"]] = (now, value)
                        fresh[value["asset"]] = value
                missing = [asset for asset in missing if asset not in fresh]
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {str(exc)[:160]}")
        return {
            "quotes": [fresh[asset] for asset in assets if asset in fresh],
            "missing": missing,
            "errors": errors,
            "providers": [provider.status() for provider in self.providers],
            "fetchedAt": utc_iso(),
            "liveOrders": False,
        }

    def status(self) -> list[dict]:
        return [provider.status() for provider in self.providers]
