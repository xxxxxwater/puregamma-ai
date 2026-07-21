"""Controlled public-web metadata search for Agent evidence gaps.

The provider never fetches user-supplied URLs or result pages. It talks only to
reviewed, fixed search endpoints and returns source metadata for citation.
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urlsplit

import feedparser
import httpx

from packages.data.provider import ProviderError, validate_public_https_url


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
_SENSITIVE_QUERY = re.compile(
    r"(?i)(BEGIN [A-Z ]*PRIVATE KEY|\b(?:api[_ -]?key|secret|password|seed phrase|mnemonic)\b\s*[:=]|\bsk-[A-Za-z0-9_-]{16,})"
)
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_EVM_ADDRESS = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
_LONG_NUMBER = re.compile(r"\b\d{10,}\b")
_HTML_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class OnlineResearchResult:
    provider: str
    publisher: str
    title: str
    snippet: str
    url: str
    published_at: datetime | None
    fetched_at: datetime


def online_research_enabled() -> bool:
    return os.getenv("AGENT_ONLINE_RESEARCH_ENABLED", "false").lower() == "true"


def online_search_candidate(query: str) -> bool:
    normalized = query.strip().lower()
    if len(normalized) < 6 or _SENSITIVE_QUERY.search(normalized):
        return False
    if normalized in {"hello", "hi there", "你好", "您好", "谢谢", "thanks"}:
        return False
    markers = (
        "?", "？", "latest", "current", "today", "news", "research", "search",
        "what", "why", "how", "when", "where", "who", "which",
        "最新", "目前", "现在", "今天", "新闻", "研究", "搜索", "查询",
        "什么", "为什么", "如何", "怎么", "哪里", "谁", "数据", "资料",
    )
    return any(marker in normalized for marker in markers)


def sanitize_online_query(query: str) -> str:
    if _SENSITIVE_QUERY.search(query):
        raise ProviderError("sensitive_query", "Sensitive content cannot be sent to online search")
    value = _EMAIL.sub(" ", query)
    value = _EVM_ADDRESS.sub(" ", value)
    value = _UUID.sub(" ", value)
    value = _LONG_NUMBER.sub(" ", value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) < 3:
        raise ProviderError("empty_query", "No safe online search terms remain")
    return value[:300]


def _clean(value: Any, limit: int) -> str:
    text = _HTML_TAG.sub(" ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def _safe_result_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        validate_public_https_url(value, {host}, resolve_dns=False)
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return None
        except ValueError:
            pass
        return value
    except ProviderError:
        return None


def _published(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class OnlineResearchProvider:
    def __init__(self, request_get: Callable[..., httpx.Response] | None = None):
        self.provider = os.getenv("ONLINE_SEARCH_PROVIDER", "google_news").strip().lower()
        self.brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
        self.timeout_seconds = min(20.0, max(2.0, float(os.getenv("ONLINE_SEARCH_TIMEOUT_SECONDS", "10") or 10)))
        self.max_results = min(10, max(1, int(os.getenv("ONLINE_SEARCH_MAX_RESULTS", "8") or 8)))
        self.max_response_bytes = min(2_000_000, max(10_000, int(os.getenv("ONLINE_SEARCH_MAX_RESPONSE_BYTES", "1000000") or 1_000_000)))
        self._request_get = request_get or httpx.get

    def search(self, query: str, *, count: int | None = None) -> list[OnlineResearchResult]:
        if not online_research_enabled():
            raise ProviderError("disabled", "Online Agent research is disabled")
        safe_query = sanitize_online_query(query)
        limit = min(self.max_results, max(1, count or self.max_results))
        if self.provider == "brave":
            if not self.brave_api_key:
                raise ProviderError("needs_key", "BRAVE_SEARCH_API_KEY is not configured")
            return self._search_brave(safe_query, limit)
        if self.provider == "google_news":
            return self._search_google_news(safe_query, limit)
        raise ProviderError("unsupported_provider", f"Unsupported online search provider: {self.provider}")

    def _get(self, url: str, *, allowed_host: str, **kwargs: Any) -> httpx.Response:
        validate_public_https_url(url, {allowed_host}, resolve_dns=False)
        response = self._request_get(
            url,
            timeout=self.timeout_seconds,
            follow_redirects=False,
            **kwargs,
        )
        if response.is_redirect:
            raise ProviderError("redirect_rejected", "Search provider redirects are not followed")
        if response.status_code == 429:
            raise ProviderError("rate_limited", "Online search rate limit reached", status_code=429)
        if response.status_code >= 400:
            raise ProviderError("http_error", f"Online search returned HTTP {response.status_code}", status_code=response.status_code)
        declared = int(response.headers.get("content-length", "0") or 0)
        if declared > self.max_response_bytes or len(response.content) > self.max_response_bytes:
            raise ProviderError("response_too_large", "Online search response exceeded size limit")
        return response

    def _search_brave(self, query: str, limit: int) -> list[OnlineResearchResult]:
        response = self._get(
            BRAVE_SEARCH_URL,
            allowed_host="api.search.brave.com",
            params={"q": query, "count": limit, "safesearch": "strict", "search_lang": "en"},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.brave_api_key,
                "User-Agent": "PureGamma AI/1.0 online-research",
            },
        )
        try:
            rows = response.json().get("web", {}).get("results", [])
        except (ValueError, AttributeError) as exc:
            raise ProviderError("invalid_response", "Online search returned invalid JSON") from exc
        fetched_at = datetime.now(timezone.utc)
        results: list[OnlineResearchResult] = []
        for row in rows:
            url = _safe_result_url(str(row.get("url") or ""))
            title = _clean(row.get("title"), 500)
            if not url or not title:
                continue
            results.append(OnlineResearchResult(
                provider="brave_web_search",
                publisher=_clean(row.get("profile", {}).get("long_name") or urlsplit(url).hostname, 160),
                title=title,
                snippet=_clean(row.get("description"), 1_000),
                url=url,
                published_at=None,
                fetched_at=fetched_at,
            ))
            if len(results) >= limit:
                break
        return results

    def _search_google_news(self, query: str, limit: int) -> list[OnlineResearchResult]:
        response = self._get(
            GOOGLE_NEWS_SEARCH_URL,
            allowed_host="news.google.com",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"Accept": "application/rss+xml", "User-Agent": "PureGamma AI/1.0 online-research"},
        )
        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ProviderError("invalid_response", "Online news search returned invalid RSS")
        fetched_at = datetime.now(timezone.utc)
        results: list[OnlineResearchResult] = []
        for row in parsed.entries:
            url = _safe_result_url(str(row.get("link") or ""))
            title = _clean(row.get("title"), 500)
            if not url or not title:
                continue
            source = row.get("source") or {}
            results.append(OnlineResearchResult(
                provider="google_news_rss",
                publisher=_clean(source.get("title") or "Google News", 160),
                title=title,
                snippet=_clean(row.get("summary") or row.get("description"), 1_000),
                url=url,
                published_at=_published(row.get("published") or row.get("updated")),
                fetched_at=fetched_at,
            ))
            if len(results) >= limit:
                break
        return results
