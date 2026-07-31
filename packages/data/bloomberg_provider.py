from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from apps.api.config import get_settings
from packages.data.enrichment import classify_topics, extract_symbols, sentiment, summarize
from packages.data.provider import DataProvider, DataSourceHealth, DataSourceStatus, ProviderDocument, ProviderError, ProviderFetchResult, ProviderUsage


AUTHORIZED_LICENSE_VALUES = {"authorized", "licensed", "active"}


class BloombergProvider(DataProvider):
    id = "bloomberg"
    name = "Bloomberg Authorized Data"
    category = "licensed_news"

    def __init__(self, *, mode: str | None = None, api_url: str | None = None, api_key: str | None = None, license_status: str | None = None, app_environment: str | None = None, request_get: Callable[..., Any] | None = None):
        settings = get_settings()
        self.mode = (mode or settings.bloomberg_mode).lower()
        self.api_url = settings.bloomberg_api_url if api_url is None else api_url
        self.api_key = settings.bloomberg_api_key if api_key is None else api_key
        self.license_status = (license_status or settings.bloomberg_license_status).lower()
        self.app_environment = app_environment or settings.app_environment
        self.redistribution_allowed = settings.bloomberg_redistribution_allowed
        self.retention_days = settings.data_retention_days
        self.timeout = settings.provider_http_timeout_seconds
        self._request_get = request_get
        self._usage = ProviderUsage()

    def health_check(self) -> DataSourceHealth:
        if self.mode == "mock":
            if self.app_environment.lower() in {"production", "prod"}:
                return DataSourceHealth(DataSourceStatus.ERROR, "Bloomberg mock mode is forbidden in production")
            return DataSourceHealth(DataSourceStatus.MOCK, "Explicit Bloomberg development mock")
        if self.mode != "production":
            return DataSourceHealth(DataSourceStatus.LICENSE_REQUIRED, "Bloomberg production integration is disabled")
        if self.license_status not in AUTHORIZED_LICENSE_VALUES:
            return DataSourceHealth(DataSourceStatus.LICENSE_REQUIRED, "Bloomberg commercial authorization is required")
        if not self.api_url or not self.api_key:
            return DataSourceHealth(DataSourceStatus.NEEDS_KEY, "Authorized Bloomberg endpoint and credentials are required")
        if not self.api_url.startswith("https://"):
            return DataSourceHealth(DataSourceStatus.ERROR, "Bloomberg production endpoint must use HTTPS")
        return DataSourceHealth(DataSourceStatus.HEALTHY, "Authorized Bloomberg connection configured")

    def get_usage(self) -> ProviderUsage:
        return self._usage

    def fetch_latest(self) -> ProviderFetchResult:
        return self.fetch_since(None)

    def fetch_since(self, cursor: str | None) -> ProviderFetchResult:
        health = self.health_check()
        if health.status == DataSourceStatus.MOCK:
            return ProviderFetchResult(documents=self._mock_documents(), next_cursor="mock-complete", http_status=200)
        if health.status != DataSourceStatus.HEALTHY:
            raise ProviderError(health.status.value.lower(), health.message)
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", "User-Agent": "PureGamma AI/1.0"}
        self._usage.requests += 1
        response = self._request_get(self.api_url, headers=headers, params=params, timeout=self.timeout) if self._request_get else httpx.get(self.api_url, headers=headers, params=params, timeout=self.timeout, follow_redirects=False)
        if response.status_code >= 400:
            raise ProviderError("http_error", f"Bloomberg authorized endpoint returned HTTP {response.status_code}", status_code=response.status_code)
        payload = response.json()
        rows = payload.get("data", payload.get("items", []))
        documents = [self._document(item) for item in rows]
        self._usage.items += len(documents)
        return ProviderFetchResult(documents=documents, next_cursor=payload.get("next_cursor"), http_status=response.status_code)

    def _document(self, item: dict) -> ProviderDocument:
        title = item.get("headline") or item.get("title") or ""
        supplied_summary = item.get("summary") or item.get("abstract") or ""
        content = item.get("content") or ""
        published = item.get("published_at") or item.get("publishedAt")
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
        text = f"{title} {supplied_summary}"
        return ProviderDocument(external_id=str(item.get("id") or item.get("story_id") or item.get("url") or title), source_name=item.get("source") or "Bloomberg", source_type="licensed_news", title=title, content=content, summary=supplied_summary, url=item.get("url") or "", author=item.get("author") or "Bloomberg", published_at=published_at, language=item.get("language") or "en", symbols=item.get("symbols") or extract_symbols(text), topics=item.get("topics") or classify_topics(text), sentiment=item.get("sentiment") or sentiment(text), credibility_score=0.95, engagement_metrics={}, raw_payload=item, license_status=self.license_status, retention_policy=f"contract-defined; local cap {self.retention_days}d", redistribution_allowed=self.redistribution_allowed)

    def _mock_documents(self) -> list[ProviderDocument]:
        now = datetime.now(timezone.utc)
        text = "Mock Bloomberg metadata: ETF flows remain a focus for Bitcoin market participants."
        return [ProviderDocument(external_id="mock-bloomberg-etf-1", source_name="Bloomberg MOCK", source_type="licensed_news_mock", title="MOCK: Bitcoin ETF flow monitor", content="", summary=summarize(text), url="", author="Bloomberg MOCK", published_at=now, symbols=["BTC"], topics=["ETF", "market"], sentiment=sentiment(text), credibility_score=0.0, raw_payload={"mock": True, "metadata_only": True}, license_status="MOCK-NOT-LICENSED-DATA", retention_policy="test-fixture-only", redistribution_allowed=False)]
