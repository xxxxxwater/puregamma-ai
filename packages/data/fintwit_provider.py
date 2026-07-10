from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apps.api.config import get_settings
from packages.data.provider import DataProvider, DataSourceHealth, DataSourceStatus, ProviderDocument, ProviderFetchResult, ProviderUsage
from packages.data.x_twitter_provider import XTwitterProvider


@dataclass(frozen=True)
class FinTwitAccountConfig:
    username: str
    display_name: str
    platform: str
    category: str
    language: str = "en"
    credibility_score: float = 0.6
    account_weight: float = 1.0
    enabled: bool = True
    source_url: str = ""
    provider_user_id: str | None = None
    collection_method: str = "official_api"


class FinTwitProvider(DataProvider):
    id = "fintwit"
    name = "FinTwit Curated Opinion Flow"
    category = "opinion"

    def __init__(self, accounts: list[FinTwitAccountConfig] | None = None, x_provider: XTwitterProvider | None = None):
        settings = get_settings()
        self.accounts = accounts if accounts is not None else self.load_accounts(settings.fintwit_config_path)
        self.x_provider = x_provider or XTwitterProvider()

    @staticmethod
    def load_accounts(path: str) -> list[FinTwitAccountConfig]:
        target = Path(path)
        if not target.exists():
            return []
        raw = yaml.safe_load(target.read_text()) or {}
        return [FinTwitAccountConfig(**item) for item in raw.get("accounts", [])]

    def health_check(self) -> DataSourceHealth:
        enabled = [item for item in self.accounts if item.enabled]
        if not enabled:
            return DataSourceHealth(DataSourceStatus.DISABLED, "No FinTwit whitelist accounts are enabled")
        official = [item for item in enabled if item.collection_method == "official_api"]
        if official and not self.x_provider.bearer_token:
            return DataSourceHealth(DataSourceStatus.NEEDS_KEY, "FinTwit official API accounts require X_BEARER_TOKEN", details={"accountCount": len(enabled)})
        unresolved = [item for item in official if not item.provider_user_id]
        if unresolved:
            return DataSourceHealth(DataSourceStatus.DEGRADED, "Some whitelist accounts need provider_user_id", details={"accountCount": len(enabled), "unresolved": len(unresolved)})
        return DataSourceHealth(DataSourceStatus.HEALTHY, "FinTwit whitelist is ready", details={"accountCount": len(enabled)})

    def get_usage(self) -> ProviderUsage:
        return self.x_provider.get_usage()

    def fetch_latest(self) -> ProviderFetchResult:
        documents: list[ProviderDocument] = []
        errors: list[str] = []
        next_cursor = None
        for account in [item for item in self.accounts if item.enabled]:
            if account.collection_method != "official_api":
                errors.append(f"@{account.username}: unsupported collection method")
                continue
            if not account.provider_user_id:
                errors.append(f"@{account.username}: provider_user_id is required")
                continue
            try:
                result = self.x_provider.fetch_user(account.provider_user_id)
                next_cursor = result.next_cursor or next_cursor
                for document in result.documents:
                    if document.author.lower() != account.username.lower():
                        continue
                    document.source_type = "fintwit_opinion"
                    document.source_name = account.display_name
                    document.credibility_score = max(0.0, min(1.0, account.credibility_score * account.account_weight))
                    document.raw_payload = {**document.raw_payload, "fintwit_category": account.category, "collection_method": account.collection_method}
                    documents.append(document)
            except Exception as exc:
                errors.append(f"@{account.username}: {str(exc)[:160]}")
        return ProviderFetchResult(documents=self.deduplicate(documents), next_cursor=next_cursor, errors=errors)

    def normalize(self, documents):
        allowlist = {item.username.lower() for item in self.accounts if item.enabled}
        return [document for document in documents if document.author.lower() in allowlist]
