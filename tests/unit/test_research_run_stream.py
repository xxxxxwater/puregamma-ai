"""The research run SSE must observe status changes committed by the worker.

Before the fix the stream re-read the run with ``db.get`` inside the
transaction opened by its ownership check, got the identity-mapped object back,
and never saw a status another session committed - so a client watching a long
research task saw "queued" until the 90 s budget ran out.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from apps.api.routers.harness_runs import run_event_stream
from packages.database.models import HarnessResearchRun
from packages.harness import compute_input_hash


def _run(db, user, status: str = "queued") -> HarnessResearchRun:
    run = HarnessResearchRun(
        user_id=user.id, status=status, requested_goal_summary="watch me",
        input_hash=compute_input_hash("watch me"), harness_version="t", runtime_version="t",
        cordis_config_hash="sha256:t", plugin_lock_hash="sha256:t", idempotency_key="stream-key", trace_id="trace-stream",
    )
    db.add(run)
    db.commit()
    return run


def _frames(stream) -> list[tuple[str, dict]]:
    out = []
    for frame in stream:
        name, _, data = frame.partition("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: ").strip())))
    return out


def test_stream_reports_statuses_the_worker_commits_from_another_session(db, normal_user):
    run = _run(db, normal_user)
    run_id = run.id  # the worker below must not touch the stream's session
    # Warm the identity map exactly like the ownership check does.
    assert db.get(HarnessResearchRun, run_id).status == "queued"
    worker = sessionmaker(bind=db.get_bind(), future=True)()
    progression = iter(["running", "validating", "completed"])
    clock = iter(range(0, 1000, 1))

    def sleep(_seconds):
        status = next(progression)
        row = worker.get(HarnessResearchRun, run_id)
        row.status = status
        worker.commit()

    user_id = normal_user.id
    frames = _frames(run_event_stream(db, user_id, run_id, "queued", "t0", sleep=sleep, clock=lambda: next(clock)))
    worker.close()
    states = [data["status"] for name, data in frames if name == "run.state"]
    assert states == ["queued", "running", "validating", "completed"]
    assert frames[-1] == ("run.completed", {"run_id": run_id, "verified": True, "degraded": False})


def test_stream_ends_with_the_last_known_state_when_the_budget_runs_out(db, normal_user):
    run = _run(db, normal_user, status="running")
    ticks = iter([0, 10, 200])
    frames = _frames(run_event_stream(db, normal_user.id, run.id, "running", "t0", sleep=lambda _s: None, clock=lambda: next(ticks), budget_seconds=90))
    assert frames[0][0] == "run.state" and frames[-1][0] == "run.state"
    assert frames[-1][1]["status"] == "running"


def test_stream_never_reports_another_users_run(db, normal_user, max_user):
    run = _run(db, normal_user)
    ticks = iter([0, 1, 2])
    frames = _frames(run_event_stream(db, max_user.id, run.id, "queued", "t0", sleep=lambda _s: None, clock=lambda: next(ticks)))
    assert frames[-1] == ("run.failed", {"run_id": run.id, "message": "run disappeared"})
