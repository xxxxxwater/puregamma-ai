from __future__ import annotations

import os

from adapters.unavailable import DisabledLiveExchangeAdapter


class CoinbaseAdvancedAdapter(DisabledLiveExchangeAdapter):
    name = "coinbase_advanced"

    def __init__(self):
        super().__init__(
            configured=bool(
                os.getenv("COINBASE_ADVANCED_API_KEY")
                and os.getenv("COINBASE_ADVANCED_API_SECRET")
            )
        )
