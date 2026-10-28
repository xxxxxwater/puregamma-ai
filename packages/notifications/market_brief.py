"""Coinbase market brief for the daily brief e-mail, served by the market-brief sidecar.

The sidecar (``market_report.py`` from puregamma-event-collector, run headless next to the
worker) collects public Coinbase and Nasdaq data and renders an email-safe HTML brief per
locale at ``GET /brief?locale=zh|en``. This module fetches it with a short timeout, checks
shape and freshness, caches it briefly per worker process and returns ``None`` on any
problem, so the daily brief falls back to the report digest instead of skipping a day.

Environment: ``MARKET_BRIEF_URL`` (empty = off), ``MARKET_BRIEF_MAX_AGE_SECONDS`` (7200),
``MARKET_BRIEF_TIMEOUT_SECONDS`` (8).

Operator commands (inside the worker image):
  python -m packages.notifications.market_brief --check
  python -m packages.notifications.market_brief --preview /tmp/brief.html --locale zh
  python -m packages.notifications.market_brief --test-send you@example.com --locale both
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request

logger = logging.getLogger("puregamma.notifications.market_brief")

CACHE_SECONDS = 120
FAILURE_BACKOFF_SECONDS = 60
MAX_RESPONSE_BYTES = 2_000_000
MAX_HTML_BYTES = 400_000
TEST_PREFIX = {"zh": "[测试] ", "en": "[Test] "}

_cache: dict[str, tuple[float, dict]] = {}
_failed_at: dict[str, float] = {}
# The sidecar is on the internal Docker network: never route it through a proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def brief_locale(locale: str | None) -> str:
    return "zh" if str(locale or "").lower().startswith("zh") else "en"


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _config() -> tuple[str, float, float]:
    url = os.environ.get("MARKET_BRIEF_URL", "").strip().rstrip("/")
    return url, _env_number("MARKET_BRIEF_MAX_AGE_SECONDS", 7200), _env_number("MARKET_BRIEF_TIMEOUT_SECONDS", 8)


def _validate(data) -> dict | None:
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None
    subject, html, text, taken_at = (data.get(key) for key in ("subject", "html", "text", "taken_at"))
    if not (isinstance(subject, str) and subject.strip() and isinstance(html, str) and html.strip()):
        return None
    if not isinstance(text, str) or isinstance(taken_at, bool) or not isinstance(taken_at, (int, float)):
        return None
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        return None
    return {
        "subject": " ".join(subject.split())[:200],
        "html": html,
        "text": text,
        "taken_at": float(taken_at),
        "snapshot_id": data.get("snapshot_id"),
        "parts": data.get("parts") if isinstance(data.get("parts"), dict) else {},
    }


def fetch_market_brief(locale: str | None, *, now: float | None = None, opener=None) -> dict | None:
    """The latest market brief for ``locale`` (zh/en), or None when off, unreachable, invalid or stale."""
    url, max_age, timeout = _config()
    if not url:
        return None
    loc = brief_locale(locale)
    now = time.time() if now is None else now
    cached = _cache.get(loc)
    if cached and 0 <= now - cached[0] < CACHE_SECONDS:
        brief = cached[1]
    else:
        if 0 <= now - _failed_at.get(loc, float("-inf")) < FAILURE_BACKOFF_SECONDS:
            return None
        try:
            with (opener or _opener).open(f"{url}/brief?locale={loc}", timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("response too large")
            brief = _validate(json.loads(raw.decode("utf-8")))
        except Exception as exc:  # HTTP, network and JSON errors all mean: use the report digest
            _failed_at[loc] = now
            logger.warning("market_brief_unavailable locale=%s error=%s status=%s", loc, type(exc).__name__, getattr(exc, "code", "-"))
            return None
        if brief is None:
            _failed_at[loc] = now
            logger.warning("market_brief_invalid locale=%s", loc)
            return None
        _cache[loc] = (now, brief)
        _failed_at.pop(loc, None)
    age = now - brief["taken_at"]
    if age > max_age:
        logger.warning("market_brief_stale locale=%s age_seconds=%d", loc, age)
        return None
    return brief


def _single_address(value: str) -> str:
    address = value.strip()
    if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", address):
        raise SystemExit(f"--test-send takes exactly one plain e-mail address, got {value!r}")
    return address


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check, preview or test-send the daily market brief e-mail.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="fetch the briefs and print a summary")
    action.add_argument("--preview", metavar="PATH", help="write the brief HTML to PATH (PATH-zh/-en with both)")
    action.add_argument("--test-send", metavar="ADDRESS", help="send the brief to this one address, subject marked as a test")
    parser.add_argument("--locale", choices=("zh", "en", "both"), default="both")
    args = parser.parse_args(argv)
    address = _single_address(args.test_send) if args.test_send else None
    locales = ("zh", "en") if args.locale == "both" else (args.locale,)
    url, max_age, _timeout = _config()
    if not url:
        print("MARKET_BRIEF_URL is not set: daily brief e-mails use the report digest")
        return 1
    failures = 0
    for loc in locales:
        _cache.pop(loc, None)
        _failed_at.pop(loc, None)
        brief = fetch_market_brief(loc)
        if not brief:
            print(f"{loc}: unavailable or older than {int(max_age)}s -> daily brief e-mails fall back to the report digest")
            failures += 1
            continue
        print(
            f"{loc}: ok · snapshot {brief['snapshot_id']} · age {int(time.time() - brief['taken_at'])}s · "
            f"html {len(brief['html'].encode('utf-8'))} bytes · parts {brief['parts']}\n    subject: {brief['subject']}"
        )
        if args.preview:
            root, ext = os.path.splitext(args.preview)
            path = args.preview if len(locales) == 1 else f"{root}-{loc}{ext or '.html'}"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(brief["html"])
            print(f"    preview written to {path}")
        if address:
            from packages.notifications.email import send_email

            subject = TEST_PREFIX[loc] + brief["subject"]
            if not send_email(address, subject, brief["text"], html=brief["html"]):
                print("    SMTP is not configured here; nothing sent")
                return 1
            print("    test e-mail sent")
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    sys.exit(main())
