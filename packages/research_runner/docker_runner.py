"""Ephemeral Docker execution for research runs (worker side, via docker CLI).

Every run executes in a fresh container with no network, a read-only root
filesystem, memory/cpu/pid caps, a runtime cap with kill, and capped output.
No production environment variables or secrets are passed; only PG_DATASET_*
variables describing the mounted read-only dataset dir are set explicitly.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
DEFAULT_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_STDIO_BYTES = 256 * 1024


def runner_image() -> str:
    return os.getenv("RESEARCH_RUNNER_IMAGE", DEFAULT_IMAGE)


def default_timeout_seconds() -> int:
    try:
        value = int(os.getenv("RESEARCH_RUNNER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(1, min(value, MAX_TIMEOUT_SECONDS))


def max_output_bytes() -> int:
    try:
        value = int(os.getenv("RESEARCH_RUNNER_MAX_OUTPUT_BYTES", str(DEFAULT_MAX_OUTPUT_BYTES)))
    except ValueError:
        return DEFAULT_MAX_OUTPUT_BYTES
    return max(1024, min(value, DEFAULT_MAX_OUTPUT_BYTES))


def job_root() -> Path:
    """Host-visible job dir root.

    When the worker itself runs in a container and spawns sibling research
    containers, this must point at a path that is bind-mounted from the host
    at the SAME absolute location (sibling containers mount host paths, never
    the worker's own filesystem). Configure RESEARCH_RUNNER_JOB_DIR
    accordingly in that topology.
    """
    root = Path(
        os.getenv("RESEARCH_RUNNER_JOB_DIR")
        or Path(tempfile.gettempdir()) / "puregamma_research_jobs"
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def container_user() -> str:
    """Optional --user for the research container (e.g. ``10001:10001``)."""
    return os.getenv("RESEARCH_RUNNER_CONTAINER_USER", "").strip()


def docker_available() -> tuple[bool, str]:
    """Honest availability probe: docker CLI plus a reachable engine socket."""
    binary = shutil.which("docker")
    if not binary:
        return False, "docker CLI not found on PATH"
    if os.environ.get("DOCKER_HOST"):
        return True, "ok"
    if os.name == "nt":
        pipe = r"\\.\pipe\docker_engine"
        if os.path.exists(pipe):
            return True, "ok"
        return False, "docker engine named pipe not found (Docker Desktop not running)"
    if os.path.exists("/var/run/docker.sock"):
        return True, "ok"
    return False, "docker socket /var/run/docker.sock not available"


@dataclass
class ContainerOutcome:
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    output_truncated: bool = False
    cancelled: bool = False
    error: str | None = None
    figures: list[Path] = field(default_factory=list)


def _read_capped(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    truncated = size > limit
    return raw[:limit].decode("utf-8", errors="replace"), truncated


def execute_in_container(
    *,
    run_id: str,
    job_dir: Path,
    data_dir: Path,
    image: str | None = None,
    timeout_seconds: int | None = None,
    max_output_bytes: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ContainerOutcome:
    """Run ``/job/run.py`` inside an ephemeral container and collect outputs.

    When ``should_cancel`` is provided it is polled once per second; the first
    truthy result kills the container and reports ``cancelled`` so the worker
    can honour a user cancellation while the run is still executing.
    """
    available, reason = docker_available()
    if not available:
        raise RuntimeError(f"docker unavailable: {reason}")
    image = image or runner_image()
    timeout = max(1, min(int(timeout_seconds or default_timeout_seconds()), MAX_TIMEOUT_SECONDS))
    container_name = f"puregamma-research-{run_id}".replace("_", "-")[:120]
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
    ]
    if container_user():
        command += ["--user", container_user()]
    command += [
        "--network",
        "none",
        "--memory",
        "512m",
        "--cpus",
        "1.0",
        "--pids-limit",
        "128",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--env",
        "PG_DATASET_DIR=/data",
        "--env",
        "MPLCONFIGDIR=/tmp",
        "--env",
        "PG_DATASETS=" + ",".join(sorted(p.name for p in data_dir.glob("*.csv"))),
        "-v",
        f"{data_dir.resolve()}:/data:ro",
        "-v",
        f"{job_dir.resolve()}:/job",
        image,
        "python",
        "/job/run.py",
    ]
    timed_out = False
    cancelled = False
    error: str | None = None

    def _kill_container() -> None:
        try:
            subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=15)
        except Exception:
            logger.warning("research_container_kill_failed name=%s", container_name)

    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        process = subprocess.Popen(command, stdout=stdout_handle, stderr=stderr_handle)
        deadline = time.monotonic() + timeout
        next_cancel_check = 0.0
        while True:
            returncode = process.poll()
            if returncode is not None:
                break
            now = time.monotonic()
            if now >= deadline:
                timed_out = True
                _kill_container()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
                break
            if should_cancel is not None and now >= next_cancel_check:
                next_cancel_check = now + 1.0
                try:
                    cancel_requested = should_cancel()
                except Exception:
                    logger.warning("research_cancel_probe_failed run_id=%s", run_id)
                    cancel_requested = False
                if cancel_requested:
                    cancelled = True
                    _kill_container()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=15)
                    break
            time.sleep(0.2)
    exit_code = process.returncode if process.returncode is not None else -1
    limit = max_output_bytes or DEFAULT_MAX_OUTPUT_BYTES
    stdout, out_trunc = _read_capped(stdout_path, min(limit, MAX_STDIO_BYTES))
    stderr, err_trunc = _read_capped(stderr_path, min(limit, MAX_STDIO_BYTES))
    out_dir = job_dir / "out"
    figures: list[Path] = []
    if out_dir.exists():
        for path in sorted(out_dir.iterdir()):
            if path.is_file() and path.name != "metrics.json" and path.stat().st_size <= limit:
                figures.append(path)
            if len(figures) >= 8:
                break
    if cancelled:
        error = "cancelled by user; container killed"
    elif timed_out:
        error = f"runtime exceeded {timeout}s; container killed"
    elif exit_code != 0:
        error = f"container exited with code {exit_code}"
    return ContainerOutcome(
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        output_truncated=out_trunc or err_trunc,
        cancelled=cancelled,
        error=error,
        figures=figures,
    )
