"""Read-only HTTP surface for the third-party Jev Trader live feed.

Three endpoints, all GET, all public and read-only. They expose only the
normalised projection built by ``apps.api.services.jev_trader_service`` -- the
upstream payload is never passed through verbatim, and no route accepts a URL,
so this cannot be turned into an open proxy.

These endpoints are deliberately independent of the TypeSafe gateway: the demo
feed being down says nothing about whether the billable Jev API is up, and vice
versa. The UI reports the two separately.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from apps.api.services.jev_trader_service import (
    EVENT_BUFFER_SIZE,
    SCHEMA_VERSION,
    get_ingestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jev-trader", tags=["jev-trader"])

#: How often the downstream stream emits a comment to stop intermediaries
#: closing an idle connection. This is OUR keepalive and says nothing about the
#: upstream: the deployed feed was not observed to send a heartbeat, so the
#: client judges freshness from event timestamps via `/status`, never from
#: whether a ping arrived.
SSE_KEEPALIVE_SECONDS = 15.0

#: How long a subscriber waits for a new event before looping.
SUBSCRIBER_WAIT_SECONDS = 1.0


@router.get("/snapshot")
def snapshot() -> dict:
    """Latest normalised state, plus the sequence number to resume from.

    A caller reads ``seq`` here and then opens ``/events?since=<seq>``. That
    closes the gap between the snapshot and the subscription; if the buffer has
    already rolled past that point the stream emits ``resync`` rather than
    silently skipping events.
    """
    return get_ingestion().snapshot()


@router.get("/status")
def status() -> dict:
    """Connection state, reported separately from data freshness."""
    return get_ingestion().status()


@router.get("/events")
def events(since: int | None = Query(default=None, ge=0)) -> StreamingResponse:
    """Server-sent events: one normalised block event per upstream block.

    Resume semantics are honest: if the caller's cursor is no longer in the
    buffer we say so and let the client re-snapshot, instead of pretending to
    have caught them up. ``Last-Event-ID`` is deliberately not used -- the
    upstream has no stable monotonic id to key on.
    """
    ingestion = get_ingestion()
    start_seq = since if since is not None else ingestion.live_seq()

    def stream() -> Iterator[str]:
        _, covered = ingestion.replay_from(start_seq)
        if not covered:
            yield _sse("resync", {"reason": "buffer_rolled", "seq": ingestion.live_seq()})
        yield _sse(
            "open",
            {
                "schema_version": SCHEMA_VERSION,
                "seq": start_seq,
                "buffer_size": EVENT_BUFFER_SIZE,
            },
        )
        cursor = start_seq
        last_keepalive = time.monotonic()
        # Starlette closes this generator when the client disconnects, which
        # raises GeneratorExit and unwinds the loop. Nothing to poll.
        while True:
            batch = ingestion.wait_for_events(cursor, SUBSCRIBER_WAIT_SECONDS)
            if not batch:
                now = time.monotonic()
                if now - last_keepalive >= SSE_KEEPALIVE_SECONDS:
                    last_keepalive = now
                    # An SSE comment, not an event: a client must not read this
                    # as evidence that the upstream is alive.
                    yield ": keepalive\n\n"
                continue
            for event in batch:
                cursor = event["seq"]
                yield _sse("event", event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Defensive: this stream must never be buffered by a proxy.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


__all__ = ["router"]
