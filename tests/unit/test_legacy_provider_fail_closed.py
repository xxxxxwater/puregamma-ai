from __future__ import annotations

import pytest

from packages.data.coingecko_provider import CoinGeckoProvider
from packages.data.coinglass_provider import CoinglassProvider
from packages.data.glassnode_provider import GlassnodeProvider
from packages.data.macro_provider import MacroProvider
from packages.data.provider import ProviderError
from packages.data.reddit_provider import RedditProvider
from packages.data.x_provider import XProvider


@pytest.mark.parametrize(
    ("call", "expected_code"),
    [
        (lambda: CoinGeckoProvider().get_snapshot(["BTC"]), "provider_unavailable"),
        (lambda: CoinglassProvider().liquidations(["BTC"]), "provider_unavailable"),
        (lambda: GlassnodeProvider().onchain_health(["BTC"]), "provider_unavailable"),
        (lambda: MacroProvider().summary(), "provider_unavailable"),
        (lambda: RedditProvider().sentiment(["BTC"]), "provider_unavailable"),
        (lambda: XProvider(bearer_token="test").scan_sentiment(["BTC"]), "legacy_placeholder_disabled"),
    ],
)
def test_legacy_placeholders_fail_closed(call, expected_code):
    with pytest.raises(ProviderError) as exc:
        call()
    assert exc.value.code == expected_code
