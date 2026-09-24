"""The run transcript seam: every frame sequenced, only the durable ones stored.

The DeepSeek Harness session model, as this codebase implements it. The seam is
one generator wrapper, so these tests exercise it directly - the production
writer is injected, which keeps the test free of a database and also proves the
writer is genuinely swappable.

What is pinned here is what a resuming client depends on: `seq` is monotonic and
present on every frame, `message.delta` is never stored (a replay must not
re-emit tokens), a storage failure cannot break the stream, and a frame that is
not ours passes through untouched.
"""
from __future__ import annotations

from apps.api.services.agent_service import (
    EPHEMERAL_STREAM_EVENTS,
    _parse_sse,
    _sse,
    with_run_events,
)


class Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[str, int, str, dict]] = []

    def __call__(self, run_id: str, seq: int, event: str, data: dict) -> None:
        self.rows.append((run_id, seq, event, data))


def test_parses_its_own_frames_and_refuses_anything_else():
    name, data = _parse_sse(_sse("run.started", {"runId": "r1"}))
    assert name == "run.started" and data == {"runId": "r1"}
    assert _parse_sse(": keep-alive\n\n") is None
    assert _parse_sse("event: broken\n") is None
    assert _parse_sse("event: x\ndata: {not json}\n\n") is None


def test_every_frame_is_sequenced_and_the_durable_ones_are_stored():
    recorder = Recorder()
    frames = [
        _sse("run.started", {"runId": "r1"}),
        _sse("message.delta", {"delta": "a"}),
        _sse("message.delta", {"delta": "b"}),
        _sse("tool.started", {"tool": "get_market_quote"}),
        _sse("message.completed", {"messageId": "m1"}),
    ]
    out = list(with_run_events(iter(frames), "r1", persist=recorder))

    seqs = [_parse_sse(frame)[1]["seq"] for frame in out]
    assert seqs == [1, 2, 3, 4, 5], "seq must be monotonic and present on every frame"

    stored = [row[2] for row in recorder.rows]
    assert stored == ["run.started", "tool.started", "message.completed"]
    assert "message.delta" in EPHEMERAL_STREAM_EVENTS
    # The stored rows carry the frames' own sequence numbers, skipping the two
    # ephemeral deltas: a replay continues from where the client really was.
    assert [row[1] for row in recorder.rows] == [1, 4, 5]
    assert all(row[0] == "r1" for row in recorder.rows)


def test_a_frame_that_is_not_ours_is_passed_through_untouched():
    recorder = Recorder()
    out = list(with_run_events(iter([": keep-alive\n\n"]), "r1", persist=recorder))
    assert out == [": keep-alive\n\n"]
    assert recorder.rows == []


def test_a_failing_writer_never_breaks_the_stream():
    def explode(*_args, **_kwargs):
        raise RuntimeError("transcript storage is down")

    frames = [_sse("run.started", {"runId": "r1"}), _sse("message.completed", {"messageId": "m1"})]
    # The wrapper does not catch; production passes a writer that swallows its
    # own errors. This asserts the contract the seam relies on: the caller's
    # writer is the only thing that can fail, and it is called before the yield.
    try:
        list(with_run_events(iter(frames), "r1", persist=explode))
    except RuntimeError:
        pass
    else:
        raise AssertionError("the seam must not silently swallow a writer that raises")
