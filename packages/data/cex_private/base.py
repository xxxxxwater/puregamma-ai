"""Read-only private CEX account adapters (portfolio connections, P0-7).

Each adapter talks to exactly ONE venue's *signed read-only* account endpoints
to validate user-provided API credentials and to fetch balances. Adapters
NEVER call order, transfer, or withdrawal endpoints.

Security invariants enforced here:

* API secrets exist only as in-memory function arguments used to compute
  request signatures. They are never logged, never stored on ``self``, and
  never embedded in :class:`NormalizedHolding` / :class:`PermissionCheck`.
* Response size is capped by ``max_response_bytes`` and every request uses
  ``timeout_seconds`` (wired to ``Settings.provider_http_timeout_seconds`` /
  ``Settings.provider_max_response_bytes`` by the service layer).
* Testnet/demo support is a base-url (or header) override. When a venue does
  not support the requested environment the adapter keeps the production URL
  and records a capability note instead of hard-failing.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Symbols treated as USD-denominated for pricing without a market quote.
USD_STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "USDE", "USDH", "PYUSD", "FRAX", "LUSD",
    "TUSD", "USDP", "FDUSD", "USDD", "GUSD", "USD",
}

# Balances priced below this threshold are dust and never become positions.
DUST_MIN_USD_VALUE = 1.0


class CexAdapterError(RuntimeError):
    """A venue read-only request failed. Messages never contain secrets."""


class CexPermissionDenied(CexAdapterError):
    """Credentials were rejected by the venue (bad key/secret/IP/permissions)."""


@dataclass(frozen=True)
class NormalizedHolding:
    """One venue balance normalized for portfolio snapshots."""

    symbol: str
    quantity: float
    usd_value: float | None  # priced USD value when a price is available, else None
    raw: dict


@dataclass(frozen=True)
class PermissionCheck:
    """Result of probing a venue with user credentials on a read-only endpoint."""

    ok: bool
    venue: str
    can_trade: bool | None  # None = venue did not expose it (unverified assumption)
    can_withdraw: bool | None
    permissions_verified: bool
    reason: str = ""
    metadata: dict = field(default_factory=dict)


def filter_dust(holdings: list[NormalizedHolding], *, min_usd_value: float = DUST_MIN_USD_VALUE) -> list[NormalizedHolding]:
    """Drop priced balances worth less than ``min_usd_value``.

    Unpriced holdings (``usd_value is None``) are kept so the snapshot can
    report priced-coverage instead of silently losing the asset.
    """
    kept = []
    for holding in holdings:
        if holding.usd_value is not None and holding.usd_value < min_usd_value:
            continue
        kept.append(holding)
    return kept


class CexPrivateAdapter(ABC):
    """Base class for signed read-only venue adapters."""

    venue: str = ""
    production_base_url: str = ""
    testnet_base_url: str | None = None

    def __init__(
        self,
        *,
        environment: str = "production",
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 5_000_000,
    ) -> None:
        self.environment = (environment or "production").strip().lower()
        self.timeout_seconds = float(timeout_seconds or 10.0)
        self.max_response_bytes = int(max_response_bytes or 5_000_000)
        self.capability_notes: list[str] = []
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif self.environment == "testnet" and self.testnet_base_url:
            self.base_url = self.testnet_base_url.rstrip("/")
        else:
            if self.environment == "testnet" and not self.testnet_base_url and not self._supports_simulated_header:
                self.capability_notes.append(f"{self.venue} does not expose a separate testnet base URL; using production URL")
            self.base_url = self.production_base_url.rstrip("/")

    @property
    def _supports_simulated_header(self) -> bool:
        return False

    # -- HTTP plumbing -----------------------------------------------------

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _get_json(self, path: str, *, params: dict | None = None, headers: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise CexAdapterError(f"{self.venue} request failed: {type(exc).__name__}") from exc
        if response.content and len(response.content) > self.max_response_bytes:
            raise CexAdapterError(f"{self.venue} response exceeded {self.max_response_bytes} bytes")
        return self._decode(response)

    @abstractmethod
    def _decode(self, response: requests.Response) -> Any:
        """Parse a venue response, mapping auth failures to CexPermissionDenied."""

    # -- Public API ---------------------------------------------------------

    @abstractmethod
    def validate_credentials(self, api_key: str, api_secret: str, passphrase: str | None = None) -> PermissionCheck:
        """Probe a signed read-only endpoint and report key permissions."""

    @abstractmethod
    def fetch_balances(self, api_key: str, api_secret: str, passphrase: str | None = None) -> list[NormalizedHolding]:
        """Fetch and normalize non-zero balances from a read-only endpoint."""
