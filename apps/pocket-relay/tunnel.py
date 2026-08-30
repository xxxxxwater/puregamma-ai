from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field

from config import settings

# 快速隧道 URL：https://<随机子域>.trycloudflare.com
# (?!api.) 负向前瞻排除保留子域 api（dsh-pocket issue #32 的坑）
QUICK_TUNNEL_URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", re.I)

_OFFICIAL_URI = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


def _platform_binary() -> tuple[str, str]:
    os_name = {"darwin": "darwin", "linux": "linux", "windows": "windows"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    return os_name, arch


def _asset_name() -> str:
    os_name, arch = _platform_binary()
    if os_name == "windows":
        return f"cloudflared-windows-{arch}.exe"
    return f"cloudflared-{os_name}-{arch}"


def binary_path() -> str:
    if settings.cloudflared_path:
        return settings.cloudflared_path
    name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    return os.path.join(settings.state_dir, name)


def _download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "PureGamma Pocket/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, "wb") as handle:
        shutil.copyfileobj(response, handle)
    if sys.platform != "win32":
        os.chmod(dest, 0o755)


def ensure_cloudflared() -> str:
    path = binary_path()
    if path and shutil.which(path or "cloudflared"):
        return path
    if os.path.exists(path):
        return path
    asset = _asset_name()
    mirrors = [f"{_OFFICIAL_URI}{asset}"] + [m.rstrip("/") + f"/{asset}" for m in settings.cloudflared_mirrors]
    errors: list[str] = []
    for url in mirrors:
        try:
            _download(url, path)
            return path
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
    raise RuntimeError("cloudflared download failed: " + "; ".join(errors[-3:]))


def _read_output(proc: subprocess.Popen, deadline: float) -> str | None:
    """从 cloudflared stdout 解析 trycloudflare URL（最多等 deadline 秒）。"""
    try:
        while time.time() < deadline and proc.poll() is None:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.2)
                continue
            match = QUICK_TUNNEL_URL_RE.search(line)
            if match:
                return match.group(0)
    except Exception:  # noqa: BLE001
        pass
    return None


@dataclass
class TunnelManager:
    proc: subprocess.Popen | None = None
    public_url: str | None = None
    started_at: float | None = None
    last_error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> str:
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return self.public_url or ""
            binary = ensure_cloudflared()
            command = [binary, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{settings.port}"]
            self.proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.started_at = time.time()
            self.last_error = None
            url = _read_output(self.proc, deadline=self.started_at + 25)
            if not url and self.proc.poll() is None:
                # 有些版本先打印启动日志，URL 稍后出现；再等一小段
                url = _read_output(self.proc, deadline=self.started_at + 40)
            if url:
                self.public_url = url
            else:
                self.last_error = "cloudflared did not produce a tunnel URL (see service log)"
            return self.public_url or ""

    def stop(self) -> None:
        with self._lock:
            proc = self.proc
            self.proc = None
            self.public_url = None
            self.started_at = None
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def status(self) -> dict:
        with self._lock:
            running = bool(self.proc and self.proc.poll() is None)
            return {
                "running": running,
                "public_url": self.public_url if running else None,
                "started_at": self.started_at,
                "last_error": self.last_error,
            }


# ---------- 自动恢复状态持久化 ----------
def _state_path() -> str:
    return os.path.join(settings.state_dir, "tunnel-state.json")


def save_auto_start(on: bool) -> None:
    os.makedirs(settings.state_dir, exist_ok=True)
    with open(_state_path(), "w", encoding="utf8") as handle:
        handle.write("1" if on else "0")


def was_auto_start() -> bool:
    try:
        with open(_state_path(), "r", encoding="utf8") as handle:
            return handle.read().strip() == "1"
    except OSError:
        return False


def auto_recover(manager: TunnelManager) -> None:
    """服务重启后自动恢复之前开着的公网隧道。"""
    if settings.auto_start_public and was_auto_start():
        try:
            manager.start()
        except Exception as exc:  # noqa: BLE001
            manager.last_error = f"auto-recover failed: {exc}"
