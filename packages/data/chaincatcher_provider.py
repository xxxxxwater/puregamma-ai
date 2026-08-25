from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import feedparser
import httpx

from apps.api.config import get_settings
from packages.data.enrichment import classify_topics, extract_symbols, sentiment, summarize
from packages.data.provider import (
    DataSourceHealth,
    DataSourceProvider,
    DataSourceStatus,
    ProviderDocument,
    ProviderError,
    ProviderFetchResult,
    ProviderUsage,
    validate_public_https_url,
)
from packages.data.rss_provider import canonical_url, clean_html


CHAINCATCHER_HOSTS = {"www.chaincatcher.com", "chaincatcher.com", "api.chaincatcher.com"}
SUPPORTED_LANGUAGES = {"zh-CN", "zh-TW", "en", "ja", "ko"}
ARTICLE_ID_RE = re.compile(r"/article/(\d+)(?:$|[/?#])")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _published(entry: dict[str, Any]) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    try:
        return _aware(parsedate_to_datetime(str(value)))
    except (TypeError, ValueError):
        return None


def _content_kind(value: str | None) -> str:
    normalized = re.sub(r"[\s_-]+", "", (value or "").strip().lower())
    return "flash" if normalized in {"flash", "快讯", "快訊", "快報", "快报", "newsflash"} else "article"


def _rss_category(entry: dict[str, Any]) -> str:
    candidates = entry.get("category") or []
    if not isinstance(candidates, (list, tuple)):
        candidates = [candidates]
    candidates = [*candidates, *(entry.get("tags") or [])]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("term") or candidate.get("label")
        if candidate:
            return str(candidate)
    return ""


def _normalize_language(value: object | None, default: str = "zh-CN") -> str:
    normalized = str(value or "").strip().replace("_", "-").lower()
    return {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hant": "zh-TW",
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
        "ja": "ja",
        "ko": "ko",
    }.get(normalized, default)


def _safe_article_url(value: str | None) -> str | None:
    if not value:
        return None
    url = canonical_url(str(value).strip())
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in CHAINCATCHER_HOSTS:
        return None
    return url


def _external_id(url: str, language: str, explicit_id: object | None = None) -> str:
    match = ARTICLE_ID_RE.search(url)
    # The canonical URL is shared by both contracts and is therefore the
    # primary merge key. REST item.id is only a fallback when a future URL
    # shape stops exposing the article id.
    article_id = str((match.group(1) if match else None) or explicit_id or "").strip()
    if not article_id:
        article_id = hashlib.sha256(url.encode()).hexdigest()[:24]
    return f"chaincatcher:{language}:{article_id}"


class ChainCatcherProvider(DataSourceProvider):
    """ChainCatcher newswire with RSS speed and REST multilingual backfill.

    The public RSS document is the low-latency path. The REST API is explicitly
    documented as approximately 15 minutes delayed, so it is rate-limited here
    and used for language coverage and metadata repair rather than polling on
    every worker tick. Full article bodies are never retained.
    """

    id = "chaincatcher"
    name = "ChainCatcher Newswire"
    category = "news"

    def __init__(
        self,
        *,
        rss_url: str | None = None,
        api_base_url: str | None = None,
        languages: tuple[str, ...] | list[str] | None = None,
        timeout_seconds: float | None = None,
        max_response_bytes: int | None = None,
        api_refresh_minutes: int | None = None,
        max_rss_items: int = 200,
        request_get: Callable[..., Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        settings = get_settings()
        self.rss_url = rss_url or settings.chaincatcher_rss_url
        self.api_base_url = (api_base_url or settings.chaincatcher_api_base_url).rstrip("/")
        configured_languages = languages or settings.chaincatcher_languages
        self.languages = tuple(language for language in configured_languages if language in SUPPORTED_LANGUAGES) or ("zh-CN", "en", "ja", "ko")
        self.timeout_seconds = timeout_seconds or settings.provider_http_timeout_seconds
        self.max_response_bytes = max_response_bytes or settings.provider_max_response_bytes
        self.api_refresh_minutes = max(5, api_refresh_minutes or settings.chaincatcher_api_refresh_minutes)
        self.max_rss_items = max(20, min(max_rss_items, 500))
        self._request_get = request_get
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._usage = ProviderUsage()
        self._last_health: DataSourceHealth | None = None

    def _default_get(self, url: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "PureGamma AI/1.0 ChainCatcher newswire"},
        ) as client:
            return client.get(url, **kwargs)

    def _request(self, url: str, **kwargs: Any) -> Any:
        host = (urlsplit(url).hostname or "").lower()
        validate_public_https_url(url, CHAINCATCHER_HOSTS, resolve_dns=False)
        if host not in CHAINCATCHER_HOSTS:
            raise ProviderError("host_not_allowed", f"ChainCatcher host is not allowed: {host}")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._usage.requests += 1
                response = (self._request_get or self._default_get)(url, **kwargs)
                status = int(response.status_code)
                if getattr(response, "is_redirect", False):
                    raise ProviderError("redirect_rejected", "ChainCatcher redirect was rejected", status_code=status)
                if status == 429:
                    retry_after = str((response.headers or {}).get("retry-after") or "").strip()
                    if retry_after.isdigit():
                        self._usage.rate_limit_reset_at = self._now() + timedelta(seconds=int(retry_after))
                    raise ProviderError("rate_limited", "ChainCatcher rate limit reached", status_code=429)
                if status >= 500:
                    raise ProviderError("http_error", f"ChainCatcher returned HTTP {status}", status_code=status)
                if status >= 400:
                    raise ProviderError("http_error", f"ChainCatcher returned HTTP {status}", status_code=status)
                content = response.content
                declared_length = int(str((response.headers or {}).get("content-length") or "0"))
                if declared_length > self.max_response_bytes or len(content) > self.max_response_bytes:
                    raise ProviderError("response_too_large", "ChainCatcher response exceeded size limit")
                return response
            except ProviderError as exc:
                if exc.code in {"rate_limited", "redirect_rejected", "response_too_large"} or (exc.status_code or 0) < 500:
                    raise
                last_error = exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            if attempt < 2:
                self._usage.retries += 1
                time.sleep(0.1 * (2**attempt))
        raise ProviderError("request_failed", str(last_error or "ChainCatcher request failed"))

    def _rss_documents(self) -> list[ProviderDocument]:
        response = self._request(self.rss_url, headers={"Accept": "application/rss+xml, application/xml;q=0.9"})
        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ProviderError("parse_error", "ChainCatcher RSS could not be parsed")
        documents: list[ProviderDocument] = []
        feed_language = _normalize_language(parsed.feed.get("language"), "zh-CN")
        for entry in parsed.entries[: self.max_rss_items]:
            url = _safe_article_url(entry.get("link") or entry.get("id"))
            title = clean_html(entry.get("title"), 500)
            if not url or not title:
                continue
            category = _rss_category(entry)
            kind = _content_kind(category)
            language = _normalize_language(entry.get("language"), feed_language)
            summary_text = clean_html(entry.get("summary") or entry.get("description"), 1200) or ""
            text = f"{title} {summary_text}"
            documents.append(
                ProviderDocument(
                    external_id=_external_id(url, language),
                    source_name="ChainCatcher",
                    source_type="flash_news" if kind == "flash" else "article",
                    title=title,
                    content="",
                    summary=summarize(summary_text or title),
                    url=url,
                    published_at=_published(entry),
                    language=language,
                    symbols=extract_symbols(text),
                    topics=classify_topics(text),
                    sentiment=sentiment(text),
                    credibility_score=0.82,
                    raw_payload={
                        "chaincatcher_id": _external_id(url, language).rsplit(":", 1)[-1],
                        "content_type": kind,
                        "category": category,
                        "ingestion_path": "rss",
                        "original": None,
                        "thumbnail": None,
                        "keywords": [],
                    },
                    license_status="linked-summary-only",
                    retention_policy="30d-metadata-and-summary",
                    redistribution_allowed=False,
                )
            )
        return documents

    def _api_documents(self, language: str) -> list[ProviderDocument]:
        response = self._request(
            f"{self.api_base_url}/news-flash",
            params={"type": "flash", "page": 1, "size": 100, "lang": language},
            headers={"Accept": "application/json"},
        )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("parse_error", "ChainCatcher API returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("result") != 1:
            message = payload.get("message") if isinstance(payload, dict) else "invalid response"
            raise ProviderError("api_error", f"ChainCatcher API error: {str(message)[:200]}")
        items = (payload.get("data") or {}).get("items")
        if not isinstance(items, list):
            raise ProviderError("parse_error", "ChainCatcher API response did not contain an item list")
        documents: list[ProviderDocument] = []
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            url = _safe_article_url(item.get("url"))
            title = clean_html(item.get("title"), 500)
            if not url or not title:
                continue
            kind = _content_kind(item.get("type"))
            summary_text = clean_html(item.get("digest") or item.get("description"), 1200) or ""
            keywords = [part.strip() for part in str(item.get("keywords") or "").split(",") if part.strip()][:20]
            text = " ".join([title, summary_text, *keywords])
            timestamp = item.get("releaseTimeStamp")
            try:
                published_at = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc) if timestamp else None
            except (TypeError, ValueError, OSError, OverflowError):
                published_at = None
            thumbnail = _safe_article_url(item.get("thumb"))
            documents.append(
                ProviderDocument(
                    external_id=_external_id(url, language, item.get("id")),
                    source_name="ChainCatcher",
                    source_type="flash_news" if kind == "flash" else "article",
                    title=title,
                    content="",
                    summary=summarize(summary_text or title),
                    url=url,
                    published_at=published_at,
                    language=language,
                    symbols=extract_symbols(text),
                    topics=classify_topics(text),
                    sentiment=sentiment(text),
                    credibility_score=0.82,
                    raw_payload={
                        "chaincatcher_id": str(item.get("id") or ""),
                        "content_type": kind,
                        "ingestion_path": "rest",
                        "original": item.get("original") if isinstance(item.get("original"), bool) else None,
                        "thumbnail": thumbnail,
                        "keywords": keywords,
                    },
                    license_status="linked-summary-only",
                    retention_policy="30d-metadata-and-summary",
                    redistribution_allowed=False,
                )
            )
        return documents

    @staticmethod
    def _cursor(value: str | None) -> dict[str, str]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _api_due(self, state: dict[str, str]) -> bool:
        value = state.get("restSyncedAt")
        if not value:
            return True
        try:
            previous = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return self._now() - (_aware(previous) or self._now()) >= timedelta(minutes=self.api_refresh_minutes)
        except ValueError:
            return True

    @staticmethod
    def _merge(documents: list[ProviderDocument]) -> list[ProviderDocument]:
        merged: dict[str, ProviderDocument] = {}
        for document in documents:
            current = merged.get(document.external_id)
            if current is None:
                merged[document.external_id] = document
                continue
            if len(document.summary) > len(current.summary):
                current.summary = document.summary
            if len(document.title) > len(current.title):
                current.title = document.title
            if document.published_at and (not current.published_at or document.published_at > current.published_at):
                current.published_at = document.published_at
            current.source_type = "flash_news" if "flash_news" in {current.source_type, document.source_type} else "article"
            current.symbols = sorted(set(current.symbols).union(document.symbols))
            current.topics = sorted(set(current.topics).union(document.topics))
            payload = dict(current.raw_payload)
            for key, value in document.raw_payload.items():
                if value not in (None, "", []):
                    payload[key] = value
            paths = set(payload.get("ingestion_paths") or [])
            paths.update(filter(None, [current.raw_payload.get("ingestion_path"), document.raw_payload.get("ingestion_path")]))
            payload["ingestion_paths"] = sorted(paths)
            current.raw_payload = payload
        return list(merged.values())

    def fetch_since(self, cursor: str | None) -> ProviderFetchResult:
        state = self._cursor(cursor)
        documents: list[ProviderDocument] = []
        errors: list[str] = []
        rss_ok = False
        try:
            documents.extend(self._rss_documents())
            rss_ok = True
        except Exception as exc:
            errors.append(f"rss: {str(exc)[:240]}")

        api_due = self._api_due(state) or not rss_ok
        api_successes = 0
        if api_due:
            for language in self.languages:
                try:
                    documents.extend(self._api_documents(language))
                    api_successes += 1
                except Exception as exc:
                    errors.append(f"rest/{language}: {str(exc)[:220]}")
            if api_successes:
                state["restSyncedAt"] = self._now().astimezone(timezone.utc).isoformat()

        documents = self._merge(documents)
        self._usage.items += len(documents)
        if errors and documents:
            self._last_health = DataSourceHealth(DataSourceStatus.DEGRADED, "; ".join(errors)[:500])
        elif errors:
            self._last_health = DataSourceHealth(DataSourceStatus.ERROR, "; ".join(errors)[:500])
        else:
            self._last_health = DataSourceHealth(
                DataSourceStatus.HEALTHY,
                f"RSS live path and {len(self.languages)} REST language path(s) configured",
            )
        return ProviderFetchResult(
            documents=documents,
            next_cursor=json.dumps(state, separators=(",", ":"), sort_keys=True),
            http_status=200 if documents else None,
            errors=errors,
        )

    def fetch_latest(self) -> ProviderFetchResult:
        return self.fetch_since(None)

    def health_check(self) -> DataSourceHealth:
        if self._last_health is not None:
            return self._last_health
        try:
            response = self._request(self.rss_url, headers={"Accept": "application/rss+xml, application/xml;q=0.9"})
            parsed = feedparser.parse(response.content)
            if not parsed.entries:
                raise ProviderError("parse_error", "ChainCatcher RSS contained no entries")
            self._last_health = DataSourceHealth(DataSourceStatus.HEALTHY, "ChainCatcher RSS is reachable")
        except Exception as exc:
            self._last_health = DataSourceHealth(DataSourceStatus.ERROR, str(exc)[:500])
        return self._last_health

    def get_usage(self) -> ProviderUsage:
        return self._usage
