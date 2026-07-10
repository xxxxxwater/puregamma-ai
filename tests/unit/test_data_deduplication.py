from __future__ import annotations

import hashlib

import pytest


def content_hash(title: str, body: str, source: str) -> str:
    normalized = ":".join(" ".join(part.lower().split()) for part in [source, title, body])
    return hashlib.sha256(normalized.encode()).hexdigest()


def test_reference_content_hash_is_stable_for_whitespace_and_case():
    first = content_hash("BTC ETF Flows", " Funding normalized ", "CoinDesk")
    second = content_hash("btc etf flows", "funding   normalized", "coindesk")

    assert first == second


@pytest.mark.contract
def test_article_deduplication_by_content_hash_contract():
    pytest.xfail("No article/post ingestion table exists yet. Expected: duplicate articles dedupe by content_hash.")


@pytest.mark.contract
def test_x_post_deduplication_by_content_hash_contract():
    pytest.xfail("No X KOL post ingestion table exists yet. Expected: duplicate posts dedupe by provider post id or content_hash.")
