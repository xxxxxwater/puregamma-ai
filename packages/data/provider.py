from __future__ import annotations

import ipaddress
import json
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import httpx


class DataSourceStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    NEEDS_KEY = "NEEDS_KEY"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    PARTIAL = "PARTIAL"
    NEED_KEY = "NEED_KEY"
    NOT_CONNECTED = "NOT_CONNECTED"
    NOT_LICENSED = "NOT_LICENSED"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"
    MOCK_DEMO = "MOCK_DEMO"
    MOCK = "MOCK"


@dataclass(frozen=True)
class DataProvenance:
    provider: str
    fetched_at: datetime
    source_url: str | None = None
    source_timestamp: datetime | None = None
    is_mock: bool = False
    is_fallback: bool = False
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "sourceUrl": self.source_url,
            "sourceTimestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "fetchedAt": self.fetched_at.isoformat(),
            "isMock": self.is_mock,
            "isFallback": self.is_fallback,
            "confidence": self.confidence,
        }


@dataclass
class DataSourceHealth:
    status: DataSourceStatus
    message: str = ""
    latency_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceSyncResult:
    status: DataSourceStatus
    records: list[Any] = field(default_factory=list)
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    errors: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ProviderUsage:
    requests: int = 0
    items: int = 0
    quota_limit: int | None = None
    quota_remaining: int | None = None
    rate_limit_reset_at: datetime | None = None
    retries: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "items": self.items,
            "quotaLimit": self.quota_limit,
            "quotaRemaining": self.quota_remaining,
            "rateLimitResetAt": self.rate_limit_reset_at.isoformat() if self.rate_limit_reset_at else None,
            "retries": self.retries,
        }


@dataclass
class ProviderDocument:
    external_id: str
    source_name: str
    source_type: str
    title: str
    content: str = ""
    summary: str = ""
    url: str = ""
    author: str = ""
    published_at: datetime | None = None
    language: str = "en"
    symbols: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    sentiment: dict[str, Any] = field(default_factory=dict)
    credibility_score: float = 0.5
    engagement_metrics: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    license_status: str = "unknown"
    retention_policy: str = "configured"
    redistribution_allowed: bool = False
    cursor: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProviderFetchResult:
    documents: list[ProviderDocument] = field(default_factory=list)
    next_cursor: str | None = None
    not_modified: bool = False
    http_status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class ProviderStatus:
    status: DataSourceStatus
    message: str = ""
    configured: bool = False
    last_http_status: int | None = None
    last_error: str | None = None
    usage: ProviderUsage = field(default_factory=ProviderUsage)


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_public_https_url(url: str, allowed_hosts: set[str], *, resolve_dns: bool = True) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host not in allowed_hosts:
        raise ProviderError("host_not_allowed", f"External host is not allowed: {host or 'missing'}")
    if host in {"localhost", "metadata.google.internal"}:
        raise ProviderError("private_host", "Private and metadata hosts are not allowed")
    try:
        literal = ipaddress.ip_address(host)
        if literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved:
            raise ProviderError("private_host", "Private IP endpoints are not allowed")
    except ValueError:
        pass
    if not resolve_dns:
        return
    try:
        for result in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(result[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise ProviderError("private_host", "Resolved address is not public")
    except socket.gaierror as exc:
        raise ProviderError("dns_error", f"DNS lookup failed for {host}") from exc


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: set[str],
        timeout_seconds: float = 10,
        max_response_bytes: int = 5_000_000,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        resolve_dns: bool = False,
    ):
        self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.retries = retries
        self.transport = transport
        self.resolve_dns = resolve_dns

    def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        validate_public_https_url(url, self.allowed_hosts, resolve_dns=self.resolve_dns)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                    transport=self.transport,
                    headers={"User-Agent": "PureGamma.ai/1.0 public-data"},
                ) as client:
                    response = client.request(method, url, **kwargs)
                if response.is_redirect:
                    raise ProviderError("redirect_rejected", "External redirects are not followed")
                if response.status_code == 429:
                    raise ProviderError("rate_limited", "Provider rate limit reached", status_code=429)
                if response.status_code >= 400:
                    raise ProviderError("http_error", f"Provider returned HTTP {response.status_code}", status_code=response.status_code)
                length = int(response.headers.get("content-length", "0") or 0)
                if length > self.max_response_bytes or len(response.content) > self.max_response_bytes:
                    raise ProviderError("response_too_large", "Provider response exceeded size limit")
                return response.json()
            except ProviderError as exc:
                if exc.code in {"rate_limited", "response_too_large", "redirect_rejected"}:
                    raise
                last_error = exc
            except (httpx.TimeoutException, httpx.NetworkError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.15 * (2**attempt))
        raise ProviderError("request_failed", str(last_error or "Provider request failed"))


class DataProvider:
    """Uniform contract for licensed, independently isolated document providers."""

    id: str
    name: str
    category: str

    @property
    def provider_name(self) -> str:
        return self.name

    @property
    def provider_type(self) -> str:
        return self.category

    def health_check(self) -> DataSourceHealth:
        raise NotImplementedError

    def fetch_latest(self) -> ProviderFetchResult:
        raise NotImplementedError

    def fetch_since(self, cursor: str | None) -> ProviderFetchResult:
        return self.fetch_latest()

    def normalize(self, documents: Iterable[ProviderDocument]) -> list[ProviderDocument]:
        return list(documents)

    def deduplicate(self, documents: Iterable[ProviderDocument]) -> list[ProviderDocument]:
        seen: set[str] = set()
        unique: list[ProviderDocument] = []
        for document in documents:
            key = document.external_id or document.url
            if key and key not in seen:
                seen.add(key)
                unique.append(document)
        return unique

    def get_usage(self) -> ProviderUsage:
        return ProviderUsage()

    def get_status(self) -> ProviderStatus:
        health = self.health_check()
        return ProviderStatus(
            status=health.status,
            message=health.message,
            configured=health.status not in {
                DataSourceStatus.NEEDS_KEY,
                DataSourceStatus.NEED_KEY,
                DataSourceStatus.LICENSE_REQUIRED,
                DataSourceStatus.NOT_LICENSED,
            },
            usage=self.get_usage(),
        )

    def sync(self) -> DataSourceSyncResult:
        fetched = self.fetch_latest()
        documents = self.deduplicate(self.normalize(fetched.documents))
        return DataSourceSyncResult(
            status=self.health_check().status,
            records=documents,
            fetched_count=len(fetched.documents),
            errors=fetched.errors,
        )


class DataSourceProvider(DataProvider):
    """Backward-compatible name for legacy market-data adapters."""


def timed_health(call: Callable[[], Any]) -> tuple[Any, int]:
    started = time.perf_counter()
    value = call()
    return value, int((time.perf_counter() - started) * 1000)
