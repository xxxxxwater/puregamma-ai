from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from apps.api.config import get_settings


router = APIRouter()
logger = logging.getLogger("puregamma.hyperliquid_stream")
UPSTREAM_URL = "wss://api.hyperliquid.xyz/ws"
INFO_URL = "https://api.hyperliquid.xyz/info"
INSTRUMENTS = (
    "xyz:CL", "xyz:BRENTOIL", "xyz:SKHX", "xyz:SP500", "xyz:XYZ100",
    "xyz:MU", "xyz:SNDK", "xyz:DRAM", "xyz:SPCX", "xyz:SKHY", "xyz:EWY",
    "BTC", "ETH", "HYPE", "ZEC", "SOL", "CASHCAT", "ONDO",
)
SNAPSHOT_TTL_SECONDS = 12
_snapshot_cache: tuple[float, list[dict]] = (0.0, [])
_snapshot_lock = asyncio.Lock()


async def _post_info(client: httpx.AsyncClient, payload: dict) -> object:
    response = await client.post(INFO_URL, json=payload)
    response.raise_for_status()
    return response.json()


async def _market_snapshot_messages() -> list[dict]:
    global _snapshot_cache
    cached_at, cached_messages = _snapshot_cache
    if cached_messages and time.monotonic() - cached_at < SNAPSHOT_TTL_SECONDS:
        return cached_messages

    async with _snapshot_lock:
        cached_at, cached_messages = _snapshot_cache
        if cached_messages and time.monotonic() - cached_at < SNAPSHOT_TTL_SECONDS:
            return cached_messages

        timeout = httpx.Timeout(15.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            main_response, xyz_response = await asyncio.gather(
                _post_info(client, {"type": "metaAndAssetCtxs"}),
                _post_info(client, {"type": "metaAndAssetCtxs", "dex": "xyz"}),
            )

            contexts: dict[str, dict] = {}
            for response in (main_response, xyz_response):
                if not isinstance(response, list) or len(response) < 2:
                    continue
                meta, asset_contexts = response[0], response[1]
                universe = meta.get("universe", []) if isinstance(meta, dict) else []
                if not isinstance(asset_contexts, list):
                    continue
                for asset, context in zip(universe, asset_contexts):
                    if isinstance(asset, dict) and isinstance(context, dict) and asset.get("name") in INSTRUMENTS:
                        contexts[str(asset["name"])] = context

            now_ms = int(time.time() * 1000)
            candle_results = await asyncio.gather(*(
                _post_info(client, {
                    "type": "candleSnapshot",
                    "req": {"coin": coin, "interval": "15m", "startTime": now_ms - 35 * 60 * 1000, "endTime": now_ms},
                })
                for coin in contexts
            ), return_exceptions=True)

        messages: list[dict] = []
        for coin, context in contexts.items():
            messages.append({"channel": "activeAssetCtx", "data": {"coin": coin, "ctx": context}})
        for coin, candles in zip(contexts, candle_results):
            if isinstance(candles, list) and candles:
                messages.append({"channel": "candle", "data": candles[-1]})
        _snapshot_cache = (time.monotonic(), messages)
        return messages


@router.websocket("/market/hyperliquid/stream")
async def hyperliquid_market_stream(websocket: WebSocket) -> None:
    """Relay the fixed, public Autopilot market watchlist from Hyperliquid."""
    settings = get_settings()
    origin = websocket.headers.get("origin", "").rstrip("/")
    if origin and origin not in settings.cors_origins:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        for message in await _market_snapshot_messages():
            await websocket.send_json(message)
        async with websockets.connect(UPSTREAM_URL, ping_interval=30, ping_timeout=20, open_timeout=10) as upstream:
            for coin in INSTRUMENTS:
                await upstream.send(json.dumps({"method": "subscribe", "subscription": {"type": "candle", "coin": coin, "interval": "15m"}}))
                await upstream.send(json.dumps({"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": coin}}))
            async for message in upstream:
                await websocket.send_text(message)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("hyperliquid_market_stream_failed", extra={"error": f"{type(exc).__name__}: {exc}"})
        try:
            await websocket.send_json({"channel": "marketFeedError", "error": type(exc).__name__})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            pass
