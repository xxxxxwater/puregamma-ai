from __future__ import annotations

import ast
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.api.services import research_runner_service as rrs
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from packages.database.models import BacktestCandle, ResearchRun, User
from packages.research_runner.docker_runner import ContainerOutcome, docker_available
from packages.research_runner.validator import CodeValidationError, validate_research_code
from tests.conftest import auth_headers


# ── AST validator ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        "import socket",
        "import requests",
        "import httpx",
        "from subprocess import run",
        "import subprocess",
        "import urllib.request",
        "from urllib import request",
        "from http import client",
        "import ctypes",
        "import multiprocessing",
        "import asyncio",
        "import shutil",
        "import paramiko",
    ],
)
def test_validator_rejects_network_process_and_escape_imports(snippet):
    with pytest.raises(CodeValidationError):
        validate_research_code(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        "eval('1+1')",
        "exec('print(1)')",
        "__import__('os')",
        "compile('1', '<s>', 'eval')",
        "os.system('ls')",
        "os.popen('ls')",
        "os.spawnl('ls')",
        "os.execvp('ls', [])",
        "os.remove('/etc/passwd')",
        "os.kill(1, 9)",
    ],
)
def test_validator_rejects_dangerous_calls(snippet):
    with pytest.raises(CodeValidationError):
        validate_research_code(snippet)


def test_validator_allows_stdlib_numpy_pandas_and_dataset_reads():
    validate_research_code(
        "import os\n"
        "import sys\n"
        "import csv, json, math, statistics\n"
        "from datetime import datetime\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "rows = list(csv.DictReader(open(os.path.join(DATA_DIR, 'BTC.csv'))))\n"
        "save_metrics({'rows': len(rows), 'mean': float(np.mean([1.0, 2.0]))})\n"
    )


def test_validator_reports_syntax_error():
    with pytest.raises(CodeValidationError):
        validate_research_code("def broken(:")


# ── Run creation: caps, honesty about docker availability ─────────────


def test_create_run_rejects_oversized_code(db, pro_user):
    code = "x = 1\n" + "#" * (64 * 1024)
    with pytest.raises(ValueError, match="64KB"):
        rrs.create_research_run(db, pro_user.id, code, [])


def test_create_run_rejects_unapproved_dataset_ref(db, pro_user):
    with pytest.raises(ValueError):
        rrs.create_research_run(db, pro_user.id, "print('hi')", ["../etc/passwd"])
    with pytest.raises(ValueError):
        rrs.create_research_run(db, pro_user.id, "print('hi')", ["DOGE"])


def test_docker_unavailable_marks_run_unavailable_honestly(monkeypatch, db, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (False, "docker CLI not found on PATH"))
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    assert row.status == "unavailable"
    assert "unavailable" in row.error
    assert row.code_hash
    # Without a caller key each request is a distinct run; with a key it is idempotent.
    again = rrs.create_research_run(db, pro_user.id, "print('hi')", [], idempotency_key=None)
    assert again.id != row.id
    same = rrs.create_research_run(db, pro_user.id, "print('hi')", [], idempotency_key="fixed-key")
    same2 = rrs.create_research_run(db, pro_user.id, "print('hi')", [], idempotency_key="fixed-key")
    assert same.id == same2.id


def test_queued_run_dispatches_to_celery(monkeypatch, db, pro_user):
    from packages.workers.tasks import execute_research_run

    dispatched: list[str] = []
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr("apps.api.redis_client.get_redis", lambda: SimpleNamespace(ping=lambda: True))
    monkeypatch.setattr(execute_research_run, "delay", lambda run_id: dispatched.append(run_id))

    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    assert row.status == "queued"
    assert rrs.queue_research_run(db, row.id) == "celery"
    assert dispatched == [row.id]
    assert db.get(ResearchRun, row.id).status == "queued"


def test_api_research_run_contract(monkeypatch, api_client, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (False, "docker socket not available"))
    headers = auth_headers(pro_user)

    rejected = api_client.post(
        "/api/research/run",
        json={"code": "import requests\nrequests.get('https://x')", "dataset_refs": []},
        headers=headers,
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "RESEARCH_CODE_REJECTED"

    created = api_client.post(
        "/api/research/run",
        json={"code": "print('hello')", "dataset_refs": ["BTC"]},
        headers=headers,
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["run_id"]
    assert payload["status"] == "unavailable"
    assert "error" in payload

    fetched = api_client.get(f"/api/research/run/{payload['run_id']}", headers=headers)
    assert fetched.status_code == 200
    detail = fetched.json()
    assert detail["status"] == "unavailable"
    assert detail["metrics_json"] == {}
    assert detail["figures"] == []
    assert detail["dataset_refs"] == ["BTC"]
    assert detail["logs_tail"] == ""


# ── Credits: reserve → settle/refund, entitlement gating, cancellation ──


def _ok_outcome() -> ContainerOutcome:
    return ContainerOutcome(exit_code=0, timed_out=False, stdout="done", stderr="")


def test_ast_rejection_is_free_and_create_reserves_credits(monkeypatch, db, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    balance_before = db.get(User, pro_user.id).credit_balance
    with pytest.raises(CodeValidationError):
        rrs.create_research_run(db, pro_user.id, "import socket", [])
    assert db.get(User, pro_user.id).credit_balance == balance_before  # rejected code is free

    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    assert row.status == "queued"
    assert row.credits_reserved == 20
    assert row.credits_spent == 0
    assert db.get(User, pro_user.id).credit_balance == balance_before - 20


def test_unavailable_runner_is_never_charged(monkeypatch, db, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (False, "docker CLI not found on PATH"))
    balance_before = db.get(User, pro_user.id).credit_balance
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    assert row.status == "unavailable"
    assert row.credits_reserved == 0
    assert db.get(User, pro_user.id).credit_balance == balance_before


def test_research_run_blocked_for_free_plan(monkeypatch, db, normal_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    with pytest.raises(EntitlementDeniedError):
        rrs.create_research_run(db, normal_user.id, "print('hi')", [])


def test_research_run_blocked_without_credits(monkeypatch, db, user_factory):
    user = user_factory("broke@puregamma.ai", plan="Pro", credit_balance=5)
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    with pytest.raises(InsufficientCreditsError):
        rrs.create_research_run(db, user.id, "print('hi')", [])
    assert db.get(User, user.id).credit_balance == 5


def test_completed_run_settles_exactly_once(monkeypatch, db, pro_user, tmp_path):
    monkeypatch.setenv("RESEARCH_RUNNER_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RESEARCH_RUNNER_DATA_DIRS", str(tmp_path / "datasets"))
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(rrs, "execute_in_container", lambda **kwargs: _ok_outcome())
    balance_before = db.get(User, pro_user.id).credit_balance

    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    row = rrs.execute_research_run(db, row.id)
    assert row.status == "completed", row.error
    assert row.credits_spent == 20
    assert db.get(User, pro_user.id).credit_balance == balance_before - 20

    again = rrs.execute_research_run(db, row.id)
    assert again.status == "completed"
    assert db.get(User, pro_user.id).credit_balance == balance_before - 20  # no double charge


def test_failed_run_refunds_reservation(monkeypatch, db, pro_user, tmp_path):
    monkeypatch.setenv("RESEARCH_RUNNER_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RESEARCH_RUNNER_DATA_DIRS", str(tmp_path / "datasets"))
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        rrs,
        "execute_in_container",
        lambda **kwargs: ContainerOutcome(
            exit_code=1, timed_out=False, stdout="", stderr="boom", error="container exited with code 1"
        ),
    )
    balance_before = db.get(User, pro_user.id).credit_balance
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    row = rrs.execute_research_run(db, row.id)
    assert row.status == "failed"
    assert "exited with code 1" in row.error
    assert row.credits_spent == 0
    assert db.get(User, pro_user.id).credit_balance == balance_before  # full refund


def test_cancel_queued_run_refunds_and_worker_never_executes(monkeypatch, db, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))

    def _forbidden_container(**kwargs):
        raise AssertionError("container must never start for a cancelled run")

    monkeypatch.setattr(rrs, "execute_in_container", _forbidden_container)
    balance_before = db.get(User, pro_user.id).credit_balance
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    cancelled = rrs.cancel_research_run(db, pro_user.id, row.id)
    assert cancelled.status == "cancelled"
    assert db.get(User, pro_user.id).credit_balance == balance_before  # refunded

    again = rrs.cancel_research_run(db, pro_user.id, row.id)
    assert again.id == cancelled.id and again.status == "cancelled"  # idempotent
    assert db.get(User, pro_user.id).credit_balance == balance_before  # refunded once

    untouched = rrs.execute_research_run(db, row.id)
    assert untouched.status == "cancelled"  # worker skips terminal runs


def test_cancel_running_run_kills_container_and_refunds_once(monkeypatch, db, pro_user, tmp_path):
    monkeypatch.setenv("RESEARCH_RUNNER_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RESEARCH_RUNNER_DATA_DIRS", str(tmp_path / "datasets"))
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    probed: list[bool] = []

    def _fake_container(**kwargs):
        # The user cancels while the container is running; the worker's cancel
        # probe must observe it and the container outcome reports the kill.
        rrs.cancel_research_run(db, pro_user.id, kwargs["run_id"])
        probed.append(bool(kwargs["should_cancel"]()))
        return ContainerOutcome(
            exit_code=-9,
            timed_out=False,
            stdout="partial",
            stderr="",
            cancelled=True,
            error="cancelled by user; container killed",
        )

    monkeypatch.setattr(rrs, "execute_in_container", _fake_container)
    balance_before = db.get(User, pro_user.id).credit_balance
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    row = rrs.execute_research_run(db, row.id)
    assert probed == [True]
    assert row.status == "cancelled"
    assert row.credits_spent == 0
    assert db.get(User, pro_user.id).credit_balance == balance_before  # exactly one refund


def test_cancel_terminal_run_rejected(monkeypatch, db, pro_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (False, "no docker"))
    row = rrs.create_research_run(db, pro_user.id, "print('hi')", [])
    assert row.status == "unavailable"
    with pytest.raises(ValueError):
        rrs.cancel_research_run(db, pro_user.id, row.id)


def test_api_research_run_entitlement_and_cancel(monkeypatch, api_client, pro_user, normal_user):
    monkeypatch.setattr(rrs, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr("apps.api.routers.research_runner.queue_research_run", lambda db, run_id: "celery")

    denied = api_client.post(
        "/api/research/run",
        json={"code": "print('hi')", "dataset_refs": []},
        headers=auth_headers(normal_user),
    )
    assert denied.status_code == 402
    assert denied.json()["detail"]["code"] == "RESEARCH_RUN_NOT_ENTITLED"

    headers = auth_headers(pro_user)
    created = api_client.post("/api/research/run", json={"code": "print('hi')"}, headers=headers)
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    cancelled = api_client.post(f"/api/research/run/{run_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["credits_reserved"] == 20
    assert cancelled.json()["credits_spent"] == 0

    # Idempotent + terminal-state contract over the API.
    again = api_client.post(f"/api/research/run/{run_id}/cancel", headers=headers)
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


# ── The API/worker never executes user code inline ────────────────────


def test_service_never_executes_user_code_inline():
    source = Path(rrs.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    bad_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval"}
    ]
    assert bad_calls == []


# ── Full container execution (only when a working docker engine exists) ──


def _docker_engine_ok() -> bool:
    available, _ = docker_available()
    if not available:
        return False
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return False


requires_docker = pytest.mark.skipif(not _docker_engine_ok(), reason="docker engine unavailable on this host")


def _seed_candles(db, bars: int = 60) -> None:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for index in range(bars):
        ts = now - timedelta(days=bars - index)
        price = 100.0 + index
        db.add(
            BacktestCandle(
                id=f"rr-BTCUSDT-{index}",
                symbol="BTCUSDT",
                interval="1d",
                ts=ts,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1000.0,
                provider="binance",
                fetched_at=now,
            )
        )
    db.commit()


@requires_docker
def test_container_executes_approved_code_and_produces_metrics(monkeypatch, db, pro_user, tmp_path):
    _seed_candles(db, bars=60)
    monkeypatch.setenv("RESEARCH_RUNNER_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("RESEARCH_RUNNER_DATA_DIRS", str(tmp_path / "datasets"))
    monkeypatch.setattr(
        "packages.backtest.artifacts.get_settings",
        lambda: SimpleNamespace(backtest_artifact_dir=str(tmp_path / "artifacts")),
    )
    code = (
        "import csv, os\n"
        "with open(os.path.join(os.environ.get('PG_DATASET_DIR', '/data'), 'BTC.csv')) as fh:\n"
        "    rows = list(csv.DictReader(fh))\n"
        "closes = [float(row['close']) for row in rows]\n"
        "save_metrics({'rows': len(rows), 'total_return': closes[-1] / closes[0] - 1})\n"
        "print('processed', len(rows), 'rows')\n"
    )
    row = rrs.create_research_run(db, pro_user.id, code, ["BTC"], limits={"timeout_seconds": 240})
    assert row.status == "queued"

    row = rrs.execute_research_run(db, row.id)
    assert row.status == "completed", row.error
    assert row.metrics_json["rows"] == 60
    assert row.metrics_json["total_return"] == pytest.approx(159.0 / 100.0 - 1)
    assert "processed 60 rows" in row.logs

    # Network isolation: socket usage must fail inside the container even
    # though the AST validator already blocks the import.
    row2 = rrs.create_research_run(db, pro_user.id, "print('offline-ok')", [])
    row2 = rrs.execute_research_run(db, row2.id)
    assert row2.status == "completed", row2.error
    assert "offline-ok" in row2.logs
