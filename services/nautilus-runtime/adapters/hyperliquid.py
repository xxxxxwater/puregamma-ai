from __future__ import annotations

import os

from adapters.unavailable import DisabledLiveExchangeAdapter


class HyperliquidAdapter(DisabledLiveExchangeAdapter):
    name = "hyperliquid"

    def __init__(self):
        super().__init__(configured=bool(os.getenv("HYPERLIQUID_WALLET_ADDRESS")))
