"""Thin client for TypeSafe's System One endpoint (model ``jev-latest``).

Why this is not an ``LLMProvider``
----------------------------------
``packages/agents/llm`` providers take a prompt and return **prose**. Jev takes
a *state* plus a map of *typed questions* and returns **structured answers**
(``choice`` / ``score`` / ``noul``) with calibrated probabilities. Nothing in
the chat path wants that shape, and putting Jev behind ``LLMProvider`` would
make it selectable from every conversation in the product. So it lives here,
with its own contract, and only the modules that genuinely need a decision
import it.

Contract notes that shaped this code
------------------------------------
* The state is evaluated **once** and every question is answered in parallel,
  so asking more questions barely costs latency. Prefer one call with many
  atomic questions over several calls.
* Input is text only -- no images or audio.
* Context is 64k tokens per request: 32k for the state plus the single longest
  question. The state builder is responsible for staying inside that.
* Output tokens are free; input is billed. Redaction and question pruning are
  therefore cost controls as well as privacy controls.
* Rate limits move around, and 429s happen. One bounded retry honouring
  ``retry-after`` is worth having; an unbounded retry loop is not.

Nothing in here decides anything. It sends questions and returns answers, or
raises :class:`JevUnavailable` -- and callers are expected to fail closed on
that rather than substitute a guess.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT_SECONDS = 20.0
#: One retry: enough for a rate-limit blip, not enough to pile up behind a
#: degraded upstream while a user waits for a page.
MAX_ATTEMPTS = 2


class JevUnavailable(RuntimeError):
    """No usable Jev client (no key, or the feature is switched off).

    Callers must treat this as "no judgment available" and say so, never as
    "assume the neutral answer".
    """


class JevError(RuntimeError):
    """The upstream call failed. Carries the status when there was one."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------
# Question builders -- the three System One primitives
# --------------------------------------------------------------------------

def noul(instructions: str, *, true_means: str | None = None,
         false_means: str | None = None) -> dict[str, Any]:
    """A yes/no question; the answer is the probability that it is true."""
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    criteria = {}
    if true_means:
        criteria["true"] = true_means
    if false_means:
        criteria["false"] = false_means
    if criteria:
        question["criteria"] = criteria
    return question


def choice(instructions: str, criteria: Mapping[str, str | None]) -> dict[str, Any]:
    """Pick one option from *criteria*; the answer carries the full distribution."""
    if not criteria:
        raise ValueError("a choice question needs at least one option")
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions: str, criteria: list[str]) -> dict[str, Any]:
    """Rate against ordered, descriptive levels.

    The returned score is a float over the level index -- 1.035 means "just
    past level 1" -- not the level itself. Round it in the caller if a
    category is what you want.
    """
    if len(criteria) < 2:
        raise ValueError("a score question needs at least two levels")
    return {"type": "score", "instructions": instructions, "criteria": list(criteria)}


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

class JevClient:
    """Synchronous System One client.

    Reads its key from the constructor or ``TYPESAFE_API_KEY``. A client with
    no key reports ``configured == False`` and refuses to call -- it never
    silently degrades into a fabricated answer.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: float | None = None,
        enabled: bool | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None
                        else os.getenv("TYPESAFE_API_KEY", "")).strip()
        self.model = (model or os.getenv("JEV_MODEL", "") or DEFAULT_MODEL).strip()
        self.endpoint = (endpoint or os.getenv("JEV_ENDPOINT", "") or DEFAULT_ENDPOINT).strip()
        if timeout_seconds is None:
            timeout_seconds = float(os.getenv("JEV_TIMEOUT_SECONDS", "") or DEFAULT_TIMEOUT_SECONDS)
        self.timeout_seconds = timeout_seconds
        # Kill switch: an operator can disable Jev without removing the key.
        if enabled is None:
            enabled = (os.getenv("JEV_ENABLED", "true").strip().lower()
                       not in {"0", "false", "no", "off"})
        self.enabled = bool(enabled)
        # `transport` is how tests drive this without a network or a key.
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and self.enabled

    @property
    def status(self) -> dict[str, Any]:
        """Safe to log and to expose on a health route: never includes the key."""
        return {
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "usable": self.configured,
            "model": self.model,
            "endpoint": self.endpoint,
        }

    def ask(self, state: Any, questions: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
        """Evaluate *questions* against *state* in one call.

        Returns ``{"model": str, "answers": {...}, "usage": {...}}`` exactly as
        the API returned it, so an answer can always be traced back to the
        versioned model id that produced it.

        Raises :class:`JevUnavailable` when unusable and :class:`JevError` when
        the call fails.
        """
        if not questions:
            raise ValueError("ask() needs at least one question")
        if not self.configured:
            raise JevUnavailable(
                "Jev is not configured (missing TYPESAFE_API_KEY or disabled)"
            )

        payload = {"state": state, "model": self.model, "questions": dict(questions)}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: str | None = None
        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self._transport,
        ) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.post(self.endpoint, json=payload, headers=headers)
                except httpx.HTTPError as exc:      # timeouts, DNS, resets
                    last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("jev transport failure (attempt %d): %s", attempt + 1, last_error)
                    continue

                if response.status_code == 200:
                    return self._parse(response)

                # Retry only what can plausibly succeed on a second try.
                if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < MAX_ATTEMPTS:
                    last_error = f"HTTP {response.status_code}"
                    logger.warning("jev retryable status %s (attempt %d)", response.status_code, attempt + 1)
                    continue

                raise JevError(
                    self._error_message(response),
                    status=response.status_code,
                )

        raise JevError(last_error or "jev call failed with no response")

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise JevError(f"jev returned non-JSON body: {exc}") from exc
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise JevError("jev response has no answers object")
        body.setdefault("usage", {})
        # `model` is the versioned id that actually answered; keep it so a
        # stored judgment can be re-checked when the alias moves.
        body.setdefault("model", "")
        return body

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        """Read the upstream message without letting it dominate the logs."""
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("message") or "")[:200]
        except ValueError:
            detail = response.text[:200]
        suffix = f": {detail}" if detail else ""
        return f"jev HTTP {response.status_code}{suffix}"
