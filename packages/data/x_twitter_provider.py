from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from apps.api.config import get_settings
from packages.data.enrichment import classify_topics, extract_symbols, sentiment, summarize
from packages.data.provider import DataProvider, DataSourceHealth, DataSourceStatus, ProviderDocument, ProviderError, ProviderFetchResult, ProviderUsage


def _utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class XTwitterProvider(DataProvider):
    id = "x-twitter"
    name = "X / Twitter Official API"
    category = "opinion"

    def __init__(self, *, bearer_token: str | None = None, base_url: str | None = None, search_query: str | None = None, list_id: str | None = None, request_budget: int | None = None, request_get: Callable[..., Any] | None = None):
        settings = get_settings()
        self.bearer_token = settings.x_bearer_token if bearer_token is None else bearer_token
        self.base_url = (base_url or settings.x_api_base_url).rstrip("/")
        self.search_query = search_query or settings.x_search_query
        self.list_id = settings.x_list_id if list_id is None else list_id
        self.request_budget = request_budget or settings.x_request_budget_per_sync
        self.timeout = settings.provider_http_timeout_seconds
        self._request_get = request_get
        self._usage = ProviderUsage()
        self._last_status: int | None = None

    def health_check(self) -> DataSourceHealth:
        if not self.bearer_token:
            return DataSourceHealth(DataSourceStatus.NEEDS_KEY, "X_BEARER_TOKEN is not configured", details={"configured": False})
        if self._last_status == 429:
            return DataSourceHealth(DataSourceStatus.DEGRADED, "X API is rate limited", details=self._usage.as_dict())
        return DataSourceHealth(DataSourceStatus.HEALTHY, "Official X API credentials configured", details=self._usage.as_dict())

    def get_usage(self) -> ProviderUsage:
        return self._usage

    def fetch_latest(self) -> ProviderFetchResult:
        return self.fetch_since(None)

    def fetch_since(self, cursor: str | None) -> ProviderFetchResult:
        if not self.bearer_token:
            raise ProviderError("needs_key", "X_BEARER_TOKEN is not configured")
        if self.list_id:
            url = f"{self.base_url}/lists/{self.list_id}/tweets"
            params: dict[str, Any] = {"max_results": 100}
        else:
            url = f"{self.base_url}/tweets/search/recent"
            params = {"query": self.search_query, "max_results": 100}
        params.update({"tweet.fields": "created_at,author_id,lang,public_metrics,entities", "expansions": "author_id", "user.fields": "id,name,username,verified,public_metrics"})
        if cursor:
            params["pagination_token"] = cursor
        response = self._get(url, params=params)
        self._last_status = response.status_code
        self._read_rate_headers(response.headers)
        if response.status_code == 429:
            raise ProviderError("rate_limited", "X API rate limit reached", status_code=429)
        if response.status_code >= 400:
            raise ProviderError("http_error", f"X API returned HTTP {response.status_code}", status_code=response.status_code)
        payload = response.json()
        users = {item["id"]: item for item in payload.get("includes", {}).get("users", [])}
        documents = [self._document(item, users.get(item.get("author_id"), {})) for item in payload.get("data", [])]
        self._usage.items += len(documents)
        return ProviderFetchResult(documents=documents, next_cursor=payload.get("meta", {}).get("next_token"), http_status=response.status_code, response_headers={key.lower(): value for key, value in response.headers.items() if key.lower().startswith("x-rate-limit")})

    def fetch_user(self, user_id: str, cursor: str | None = None) -> ProviderFetchResult:
        if not self.bearer_token:
            raise ProviderError("needs_key", "X_BEARER_TOKEN is not configured")
        params: dict[str, Any] = {"max_results": 100, "tweet.fields": "created_at,author_id,lang,public_metrics,entities", "expansions": "author_id", "user.fields": "id,name,username,verified,public_metrics", "exclude": "retweets,replies"}
        if cursor:
            params["pagination_token"] = cursor
        response = self._get(f"{self.base_url}/users/{user_id}/tweets", params=params)
        self._last_status = response.status_code
        self._read_rate_headers(response.headers)
        if response.status_code == 429:
            raise ProviderError("rate_limited", "X API rate limit reached", status_code=429)
        if response.status_code >= 400:
            raise ProviderError("http_error", f"X API returned HTTP {response.status_code}", status_code=response.status_code)
        payload = response.json()
        users = {item["id"]: item for item in payload.get("includes", {}).get("users", [])}
        documents = [self._document(item, users.get(item.get("author_id"), {})) for item in payload.get("data", [])]
        self._usage.items += len(documents)
        return ProviderFetchResult(documents=documents, next_cursor=payload.get("meta", {}).get("next_token"), http_status=response.status_code)

    def _get(self, url: str, **kwargs: Any):
        if self._usage.requests >= self.request_budget:
            raise ProviderError("budget_exhausted", "X request budget exhausted for this sync")
        self._usage.requests += 1
        headers = {"Authorization": f"Bearer {self.bearer_token}", "User-Agent": "PureGamma AI/1.0"}
        if self._request_get:
            return self._request_get(url, headers=headers, timeout=self.timeout, **kwargs)
        return httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=False, **kwargs)

    def _read_rate_headers(self, headers: Any) -> None:
        try:
            self._usage.quota_limit = int(headers.get("x-rate-limit-limit")) if headers.get("x-rate-limit-limit") else None
            self._usage.quota_remaining = int(headers.get("x-rate-limit-remaining")) if headers.get("x-rate-limit-remaining") else None
            reset = headers.get("x-rate-limit-reset")
            self._usage.rate_limit_reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc) if reset else None
        except (TypeError, ValueError):
            pass

    def _document(self, item: dict, user: dict) -> ProviderDocument:
        text = item.get("text", "")
        author = user.get("username") or item.get("author_id", "")
        tweet_id = str(item.get("id", ""))
        published = _utc(item.get("created_at"))
        return ProviderDocument(external_id=tweet_id, source_name=f"@{author}" if author else "X", source_type="social_opinion", title=summarize(text, 180), content=text, summary=summarize(text), url=f"https://x.com/{author}/status/{tweet_id}" if author else f"https://x.com/i/web/status/{tweet_id}", author=author, published_at=published, language=item.get("lang") or "und", symbols=extract_symbols(text), topics=classify_topics(text), sentiment=sentiment(text), credibility_score=0.55, engagement_metrics=item.get("public_metrics") or {}, raw_payload=item, license_status="x-developer-agreement", retention_policy="provider-policy-and-configured-retention", redistribution_allowed=False, cursor=tweet_id)
