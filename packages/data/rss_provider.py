from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
import yaml

from apps.api.config import get_settings
from packages.data.enrichment import classify_topics, extract_symbols, sentiment, summarize
from packages.data.provider import DataProvenance, DataSourceHealth, DataSourceProvider, DataSourceStatus, DataSourceSyncResult, ProviderDocument, ProviderError, ProviderFetchResult, ProviderUsage, validate_public_https_url


SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
SYMBOLS = ("BTC", "ETH", "HYPE", "MSTR", "STRC")


@dataclass(frozen=True)
class RSSSource:
    id: str
    name: str
    url: str
    language: str = "en"
    enabled: bool = True
    credibility_score: float = 0.65
    source_license: str = "linked-summary-only"
    redistribution_allowed: bool = False
    retention_policy: str = "30d-metadata-and-summary"


def clean_html(value: str | None, limit: int = 1200) -> str | None:
    if not value:
        return None
    cleaned = SCRIPT_RE.sub(" ", value)
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", html.unescape(cleaned)).strip()
    return cleaned[:limit] or None


def canonical_url(value: str) -> str:
    parts = urlsplit(value)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def _published(entry: dict) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class RSSProvider(DataSourceProvider):
    id = "rss"
    name = "RSS News"
    category = "news"

    def __init__(self, sources: list[RSSSource] | None = None, timeout_seconds: float | None = None, max_response_bytes: int | None = None, validators: dict[str, dict[str, str]] | None = None):
        settings = get_settings()
        self.sources = sources or self.load_sources(settings.rss_config_path)
        self.timeout_seconds = timeout_seconds or settings.rss_request_timeout
        self.max_response_bytes = max_response_bytes or settings.provider_max_response_bytes
        self._validators: dict[str, dict[str, str]] = validators or {}
        self._usage = ProviderUsage()

    @staticmethod
    def load_sources(path: str) -> list[RSSSource]:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return [RSSSource(**item) for item in raw.get("sources", []) if item.get("enabled", True)]

    def _fetch(self, source: RSSSource) -> bytes | None:
        host = urlsplit(source.url).hostname or ""
        validate_public_https_url(source.url, {host}, resolve_dns=False)
        headers = {"User-Agent": "PureGamma AI/1.0 RSS", **self._validators.get(source.id, {})}
        last_error: Exception | None = None
        response = None
        for attempt in range(3):
            try:
                self._usage.requests += 1
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False, headers=headers) as client:
                    response = client.get(source.url)
                if response.status_code < 500:
                    break
                last_error = ProviderError("http_error", f"{source.name} returned HTTP {response.status_code}", status_code=response.status_code)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            if attempt < 2:
                self._usage.retries += 1
                __import__("time").sleep(0.1 * (2**attempt))
        if response is None:
            raise ProviderError("request_failed", str(last_error or "RSS request failed"))
        if response.status_code == 304:
            return None
        if response.status_code == 429:
            raise ProviderError("rate_limited", f"{source.name} rate limited", status_code=429)
        if response.status_code >= 400 or response.is_redirect:
            raise ProviderError("http_error", f"{source.name} returned HTTP {response.status_code}", status_code=response.status_code)
        if len(response.content) > self.max_response_bytes:
            raise ProviderError("response_too_large", f"{source.name} response exceeded size limit")
        validators = {}
        if response.headers.get("etag"):
            validators["If-None-Match"] = response.headers["etag"]
        if response.headers.get("last-modified"):
            validators["If-Modified-Since"] = response.headers["last-modified"]
        if validators:
            self._validators[source.id] = validators
        return response.content

    @property
    def validators(self) -> dict[str, dict[str, str]]:
        return self._validators

    def get_usage(self) -> ProviderUsage:
        return self._usage

    def fetch_latest(self) -> ProviderFetchResult:
        documents: list[ProviderDocument] = []
        errors: list[str] = []
        unchanged = 0
        for source in self.sources:
            try:
                content = self._fetch(source)
                if content is None:
                    unchanged += 1
                    continue
                parsed = feedparser.parse(content)
                if getattr(parsed, "bozo", False) and not parsed.entries:
                    raise ProviderError("parse_error", f"{source.name} feed could not be parsed")
                for entry in parsed.entries[:100]:
                    title = clean_html(entry.get("title"), 500)
                    url = entry.get("link")
                    if not title or not url:
                        continue
                    body = clean_html(entry.get("content", [{}])[0].get("value") if entry.get("content") else entry.get("summary") or entry.get("description"), 5000) or ""
                    text = f"{title} {body}"
                    documents.append(ProviderDocument(
                        external_id=str(entry.get("id") or canonical_url(url)),
                        source_name=source.name,
                        source_type="rss_news",
                        title=title,
                        content=body,
                        summary=summarize(body or title),
                        url=canonical_url(url),
                        author=clean_html(entry.get("author"), 200) or "",
                        published_at=_published(entry),
                        language=source.language,
                        symbols=extract_symbols(text),
                        topics=classify_topics(text),
                        sentiment=sentiment(text),
                        credibility_score=source.credibility_score,
                        raw_payload={"id": entry.get("id"), "title": title, "link": url, "summary": body},
                        license_status=source.source_license,
                        retention_policy=source.retention_policy,
                        redistribution_allowed=source.redistribution_allowed,
                    ))
            except Exception as exc:
                errors.append(f"{source.name}: {str(exc)[:240]}")
        self._usage.items += len(documents)
        return ProviderFetchResult(documents=self.deduplicate(documents), not_modified=unchanged == len(self.sources), errors=errors)

    def health_check(self) -> DataSourceHealth:
        if not self.sources:
            return DataSourceHealth(DataSourceStatus.NOT_CONNECTED, "No RSS feeds configured")
        try:
            self._fetch(self.sources[0])
            return DataSourceHealth(DataSourceStatus.HEALTHY, f"{len(self.sources)} feeds configured")
        except ProviderError as exc:
            status = DataSourceStatus.RATE_LIMITED if exc.code == "rate_limited" else DataSourceStatus.ERROR
            return DataSourceHealth(status, str(exc))

    def sync(self) -> DataSourceSyncResult:
        fetched = self.fetch_latest()
        records: list[dict] = []
        for document in fetched.documents:
            score = float(document.sentiment.get("score", 0))
            fetched_at = document.fetched_at
            records.append({"source": document.source_name, "external_id": document.external_id, "title": document.title, "summary": document.summary, "url": document.url, "canonical_url": document.url, "author": document.author or None, "published_at": document.published_at, "fetched_at": fetched_at, "content_hash": hashlib.sha256(f"{document.url}\n{document.title}".encode()).hexdigest(), "language": document.language, "sentiment_score": score, "sentiment_label": document.sentiment.get("label", "neutral"), "related_symbols": document.symbols, "provenance_json": DataProvenance(provider="rss", source_url=document.url, source_timestamp=document.published_at, fetched_at=fetched_at).as_dict()})
        status = DataSourceStatus.ERROR if fetched.errors and not records else DataSourceStatus.DEGRADED if fetched.errors else DataSourceStatus.HEALTHY
        return DataSourceSyncResult(status=status, records=records, fetched_count=len(records), errors=fetched.errors)

    def headlines(self) -> list[str]:
        """Backward-compatible real-feed headline view."""
        return [record["title"] for record in self.sync().records]
