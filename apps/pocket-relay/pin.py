from __future__ import annotations

import os
import re
import secrets

from config import settings

PIN_RE = re.compile(r"^\d{8}$")


def _ensure_state() -> None:
    os.makedirs(settings.state_dir, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(settings.state_dir, name)


def _read_pin(name: str) -> str | None:
    try:
        with open(_path(name), "r", encoding="utf8") as handle:
            value = handle.read().strip()
        return value if PIN_RE.match(value) else None
    except OSError:
        return None


def _write_pin(name: str, value: str) -> str:
    _ensure_state()
    with open(_path(name), "w", encoding="utf8") as handle:
        handle.write(value)
    return value


def new_pin() -> str:
    return f"{secrets.randbelow(90000000) + 10000000}"


def _custom_flag_path(which: str) -> str:
    return _path(f"pin-{which}-custom")


def _is_custom(which: str) -> bool:
    try:
        return open(_custom_flag_path(which), "r", encoding="utf8").read().strip() == "1"
    except OSError:
        return False


def _set_custom(which: str, on: bool) -> None:
    _ensure_state()
    with open(_custom_flag_path(which), "w", encoding="utf8") as handle:
        handle.write("1" if on else "0")


# ---------- 公网 PIN（token） ----------
def get_public_pin() -> str:
    return _read_pin("token") or _write_pin("token", new_pin())


def rotate_public_pin() -> str:
    # 用户自定义后不再轮换（尊重自定义值）
    if _is_custom("public"):
        return get_public_pin()
    return _write_pin("token", new_pin())


# ---------- 局域网 PIN（token-lan） ----------
def get_lan_pin() -> str:
    return _read_pin("token-lan") or _write_pin("token-lan", new_pin())


def refresh_lan_pin() -> str:
    _set_custom("lan", False)
    return _write_pin("token-lan", new_pin())


# ---------- 自定义 PIN ----------
def set_custom_pin(which: str, value: str) -> str:
    value = value.strip()
    if not PIN_RE.match(value):
        raise ValueError("PIN must be exactly 8 digits")
    if which == "public":
        _write_pin("token", value)
        _set_custom("public", True)
        return value
    if which == "lan":
        _write_pin("token-lan", value)
        _set_custom("lan", True)
        return value
    raise ValueError("unknown PIN kind")


def pin_is_custom(which: str) -> bool:
    return _is_custom(which)


# ---------- 按 Host 分发 PIN ----------
def pin_for_host(host: str | None) -> str:
    # 公网隧道（trycloudflare）用公网密码，其余（局域网/直连）用局域网密码
    if host and host.endswith("trycloudflare.com"):
        return get_public_pin()
    return get_lan_pin()
