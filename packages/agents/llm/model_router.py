from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from apps.api.config import Settings, get_settings
from packages.agents.llm.base import LLMProvider
from packages.agents.llm.cost_tracker import log_llm_call, redact_text
from packages.agents.llm.deepseek_provider import DeepSeekProvider
from packages.agents.llm.kimi_provider import KimiProvider
from packages.agents.llm.mock_provider import MockLLMProvider
from packages.agents.llm.openai_provider import OpenAIProvider
from packages.agents.llm.schemas import ChatMessage, LLMResponse


class ModelRouterUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRoute:
    provider_name: str
    model: str
    reason: str


# Fast chat / classification / summaries -> deepseek.
DEEPSEEK_TASK_TYPES = frozenset({
    "agent_chat",
    "secretary_dialog",
    "default_chat",
    "daily_market_report",
    "classification",
    "summarization",
})
# Deep causal analysis / portfolio risk / strategy + backtest review -> luna (openai).
LUNA_TASK_TYPES = frozenset({
    "portfolio_risk_review",
    "strategy_review",
    "backtest_review",
    "luna_research",
})
# Long-context multi-document synthesis -> kimi.
KIMI_TASK_TYPES = frozenset({
    "agent_deep_research",
    "deep_research",
    "document_synthesis",
    "source_crosscheck",
    "kimi_research",
})


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


class ModelRouter:
    """Task-type based multi-model router with structured degradation.

    Providers are called with db=None so they never log twice; the router
    persists exactly one LLMCallLog per attempt, including latency_ms.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def route_for_task(self, task_type: str, *, plan: str | None = None) -> ModelRoute:
        settings = self.settings
        if task_type in KIMI_TASK_TYPES:
            return ModelRoute("kimi", settings.kimi_model or "kimi-k3", "long_context_synthesis")
        if task_type in LUNA_TASK_TYPES:
            return ModelRoute("openai", settings.openai_luna_model, "deep_analysis")
        if task_type in DEEPSEEK_TASK_TYPES:
            return ModelRoute("deepseek", settings.deepseek_model or "deepseek-v4-flash", "fast_task")
        return ModelRoute("deepseek", settings.deepseek_model or "deepseek-v4-flash", "default")

    # ------------------------------------------------------------------
    # Provider builders
    # ------------------------------------------------------------------
    def _deepseek_provider(self) -> LLMProvider:
        return DeepSeekProvider(self.settings)

    def _openai_provider(self) -> LLMProvider:
        return OpenAIProvider(self.settings)

    def _kimi_provider(self) -> LLMProvider:
        return KimiProvider(self.settings)

    def _luna_provider(self, plan: str | None = None) -> LLMProvider:
        settings = self.settings
        provider = OpenAIProvider(
            settings,
            model=settings.openai_luna_model,
            timeout_seconds=settings.openai_luna_timeout_seconds,
            reasoning_effort=settings.openai_luna_reasoning_effort,
        )
        if not settings.openai_luna_enabled:
            provider.configured = False
            provider.last_error = "OPENAI_LUNA_ENABLED is false"
        elif plan is not None and plan.lower() not in {item.lower() for item in settings.openai_luna_allowed_plans}:
            provider.configured = False
            provider.last_error = "plan not allowed for Luna"
        return provider

    def _fallback_chain(self, route: ModelRoute, plan: str | None) -> list[tuple[str, Callable[[], LLMProvider]]]:
        routed: tuple[str, Callable[[], LLMProvider]]
        if route.provider_name == "kimi":
            routed = ("kimi", self._kimi_provider)
        elif route.provider_name == "openai":
            routed = ("openai", lambda: self._luna_provider(plan))
        else:
            routed = ("deepseek", self._deepseek_provider)
        chain = [routed]
        for label, builder in (("deepseek", self._deepseek_provider), ("openai", self._openai_provider)):
            if label != routed[0]:
                chain.append((label, builder))
        return chain

    # ------------------------------------------------------------------
    # Logging helper (single row per attempt, with latency)
    # ------------------------------------------------------------------
    def _logged_call(
        self,
        provider: LLMProvider,
        messages: list[ChatMessage],
        *,
        task_type: str,
        locale: str,
        user_id: str | None,
        db: Session | None,
        response_format: str | None = None,
    ) -> tuple[LLMResponse | None, int, str | None]:
        prompt = "\n".join(message.content for message in messages)
        started = time.perf_counter()
        try:
            response = provider.chat(messages, task_type=task_type, locale=locale, user_id=user_id, db=None, response_format=response_format)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            error = redact_text(str(exc))
            log_llm_call(db, user_id=user_id, provider=provider.provider_name, model=provider.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=max(1, len(prompt.split())), completion_tokens=0, status="failed", error_message=error, latency_ms=latency_ms)
            return None, latency_ms, error
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_llm_call(db, user_id=user_id, provider=provider.provider_name, model=provider.model, task_type=task_type, locale=locale, prompt=prompt, prompt_tokens=response.prompt_tokens, completion_tokens=response.completion_tokens, status="success", latency_ms=latency_ms)
        return response, latency_ms, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def complete(
        self,
        messages: list[ChatMessage],
        *,
        task_type: str,
        locale: str = "en",
        user_id: str | None = None,
        db: Session | None = None,
        plan: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        route = self.route_for_task(task_type, plan=plan)
        failures: list[str] = []
        configured_chain: list[tuple[str, LLMProvider]] = []
        for label, builder in self._fallback_chain(route, plan):
            provider = builder()
            if not provider.configured:
                failures.append(f"{label} not configured: {provider.last_error}")
                continue
            configured_chain.append((label, provider))
        if not configured_chain:
            if self.settings.app_environment.lower() != "production":
                mock = MockLLMProvider(status="fallback_mock", last_error="no real provider configured")
                response = mock.chat(messages, task_type=task_type, locale=locale, user_id=user_id, db=db, response_format=response_format)
                response.metadata.update({"degraded": True, "requested_provider": route.provider_name, "reason": "no_real_provider_configured"})
                return response
            raise ModelRouterUnavailable("NO_PROVIDER_CONFIGURED")
        for label, provider in configured_chain:
            response, _, error = self._logged_call(provider, messages, task_type=task_type, locale=locale, user_id=user_id, db=db, response_format=response_format)
            if response is None:
                failures.append(f"{label} call failed: {error}")
                continue
            if failures or label != route.provider_name:
                response.metadata.update({"degraded": True, "requested_provider": route.provider_name, "reason": "; ".join(failures)})
            return response
        raise ModelRouterUnavailable("ALL_PROVIDERS_FAILED: " + "; ".join(failures))

    def deep_research(
        self,
        evidence_pack: dict,
        *,
        locale: str = "en",
        user_id: str | None = None,
        db: Session | None = None,
        plan: str | None = None,
    ) -> dict:
        evidence_json = json.dumps(evidence_pack, ensure_ascii=False, default=str)
        evidence_refs = evidence_pack.get("evidence_refs") or evidence_pack.get("refs") or []
        traces: list[dict] = []
        skipped: list[dict] = []

        def _skip(provider_name: str, model: str, task_type: str, reason: str | None) -> None:
            skipped.append({"provider": provider_name, "model": model, "task_type": task_type, "reason": reason or "unavailable"})

        def _run_step(provider: LLMProvider, *, task_type: str, messages: list[ChatMessage], response_format: str | None = None) -> str | None:
            response, latency_ms, error = self._logged_call(provider, messages, task_type=task_type, locale=locale, user_id=user_id, db=db, response_format=response_format)
            traces.append({"provider": provider.provider_name, "model": provider.model, "task_type": task_type, "latency_ms": latency_ms, "status": "success" if response is not None else "failed"})
            if response is None:
                _skip(provider.provider_name, provider.model, task_type, error)
                return None
            return response.content

        # Step 1: Kimi synthesizes the evidence pack and extracts agreements/contradictions.
        kimi_task = "deep_research_kimi_synthesis"
        kimi = self._kimi_provider()
        kimi_synthesis: str | None = None
        contradictions: list[str] = []
        if not kimi.configured:
            _skip("kimi", kimi.model, kimi_task, kimi.last_error)
        else:
            kimi_prompt = (
                "You are the long-context synthesis model in a multi-model research pipeline. "
                "Synthesize the following structured evidence pack. Extract cross-source agreements and contradictions. "
                "Respond as JSON with keys: synthesis (string), agreements (list of strings), contradictions (list of strings).\n"
                f"Evidence pack:\n{evidence_json}"
            )
            raw = _run_step(kimi, task_type=kimi_task, messages=[ChatMessage(role="user", content=kimi_prompt)], response_format="json_object")
            if raw is not None:
                parsed = _parse_json_object(raw)
                kimi_synthesis = str(parsed.get("synthesis") or raw)
                contradictions = _as_str_list(parsed.get("contradictions"))

        # Step 2: Luna performs causal/risk/strategy counter-review of Kimi's synthesis and the evidence.
        luna_task = "deep_research_luna_review"
        luna = self._luna_provider(plan)
        luna_review: str | None = None
        if not luna.configured:
            _skip("openai", luna.model, luna_task, luna.last_error)
        else:
            luna_prompt = (
                "You are the deep-analysis counter-review model in a multi-model research pipeline. "
                "Critically review the synthesis below for causal flaws, portfolio risk blind spots, and strategy/backtest weaknesses. "
                "Explicitly state where you disagree with the synthesis.\n"
                f"Synthesis under review:\n{kimi_synthesis or '(kimi synthesis unavailable)'}\n"
                f"Evidence pack:\n{evidence_json}"
            )
            luna_review = _run_step(luna, task_type=luna_task, messages=[ChatMessage(role="user", content=luna_prompt)])

        # Step 3: DeepSeek (fallback: OpenAI) merges everything into the final conclusion.
        final_task = "deep_research_final_synthesis"
        synthesis_prompt = (
            "You are the final synthesis model in a multi-model research pipeline. "
            "Merge the inputs below into one final conclusion. List model disagreements explicitly.\n"
            f"Kimi synthesis:\n{kimi_synthesis or '(unavailable)'}\n"
            f"Extracted contradictions:\n{json.dumps(contradictions, ensure_ascii=False)}\n"
            f"Luna counter-review:\n{luna_review or '(unavailable)'}\n"
            f"Evidence pack:\n{evidence_json}"
        )
        conclusion = ""
        synthesizer_ran = False
        for provider in (self._deepseek_provider(), self._openai_provider()):
            if not provider.configured:
                _skip(provider.provider_name, provider.model, final_task, provider.last_error)
                continue
            synthesizer_ran = True
            result = _run_step(provider, task_type=final_task, messages=[ChatMessage(role="user", content=synthesis_prompt)])
            if result is not None:
                conclusion = result
                break
        if not synthesizer_ran and not any(item["task_type"] == final_task for item in skipped):
            _skip("deepseek", self.settings.deepseek_model or "deepseek-v4-flash", final_task, "unavailable")

        return {
            "conclusion": conclusion,
            "disagreements": contradictions,
            "model_traces": traces,
            "evidence_refs": evidence_refs,
            "degraded": bool(skipped),
            "skipped_models": skipped,
        }

    def router_status(self) -> dict:
        settings = self.settings
        deepseek = DeepSeekProvider(settings)
        kimi = KimiProvider(settings)
        luna = self._luna_provider()

        def _host(url: str) -> str:
            return urlparse(url).hostname or ""

        return {
            "providers": {
                "deepseek": {
                    "configured": deepseek.configured,
                    "model": deepseek.model,
                    "base_url_host_only": _host(deepseek.base_url),
                    "enabled": True,
                },
                "openai": {
                    "configured": luna.configured,
                    "model": luna.model,
                    "base_url_host_only": _host(settings.openai_base_url) if settings.openai_base_url else "api.openai.com",
                    "enabled": bool(settings.openai_luna_enabled),
                },
                "kimi": {
                    "configured": kimi.configured,
                    "model": kimi.model,
                    "base_url_host_only": _host(kimi.base_url),
                    "enabled": bool(settings.kimi_enabled),
                },
            },
            "routing": {
                "deepseek": sorted(DEEPSEEK_TASK_TYPES),
                "openai": sorted(LUNA_TASK_TYPES),
                "kimi": sorted(KIMI_TASK_TYPES),
                "default": "deepseek",
            },
            "fallback_chain": ["routed", "deepseek", "openai"],
        }
