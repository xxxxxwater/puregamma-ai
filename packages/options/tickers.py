from __future__ import annotations

MEGA_CAP_OPTIONS: dict[str, dict] = {
    "BTC": {"provider": "deribit", "label": "Bitcoin", "market_cap": "Crypto"},
    "ETH": {"provider": "deribit", "label": "Ethereum", "market_cap": "Crypto"},
    "AAPL": {"provider": "polygon", "label": "Apple Inc.", "market_cap": "$3.2T"},
    "MSFT": {"provider": "polygon", "label": "Microsoft Corp.", "market_cap": "$3.0T"},
    "NVDA": {"provider": "polygon", "label": "NVIDIA Corp.", "market_cap": "$2.8T"},
    "GOOGL": {"provider": "polygon", "label": "Alphabet Inc.", "market_cap": "$2.1T"},
    "AMZN": {"provider": "polygon", "label": "Amazon.com Inc.", "market_cap": "$1.9T"},
    "META": {"provider": "polygon", "label": "Meta Platforms", "market_cap": "$1.5T"},
    "TSLA": {"provider": "polygon", "label": "Tesla Inc.", "market_cap": "$0.7T"},
    "MSTR": {"provider": "polygon", "label": "Strategy (MSTR)", "market_cap": "$0.08T"},
}


def surface_tickers() -> list[dict]:
    return [
        {"symbol": symbol, **meta}
        for symbol, meta in MEGA_CAP_OPTIONS.items()
    ]
