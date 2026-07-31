"""Deterministic declarative workflow engine for official Skills (P0-6).

Workflows are data, not code: each official Skill bundle ships a
``workflows/<slug>.yaml`` step DAG and this module is the single engine that
executes it. Steps map to read-only tools over existing services and stored
data. The engine itself performs no LLM calls and never fabricates data:
unavailable sources surface as degraded step markers, and every step records
{status, started_at, latency_ms, evidence_refs, error} into
``SkillRun.evidence_json["workflow"]``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import yaml
from sqlalchemy.orm import Session

from packages.database.models import (
    AccountSnapshot,
    Alert,
    BacktestRun,
    CreditBudgetPolicy,
    MarketEvent,
    MarketQuoteRecord,
    NormalizedDocument,
    OrderIntent,
    Signal,
    StrategyRun,
    TradingAccount,
    User,
    utcnow,
)
from packages.skills.manifest import SkillManifest
from packages.skills.policy import NEVER_IMPORTED_TOOLS, READ_ONLY_SKILL_TOOLS, REVIEWED_OFFICIAL_TOOLS

POLICY_TOOL_NAMES = READ_ONLY_SKILL_TOOLS | REVIEWED_OFFICIAL_TOOLS

STEP_ON_FAILURE = ("abort", "degrade")
OPEN_ORDER_INTENT_STATUSES = ("PREVIEWED", "PENDING", "APPROVED", "SUBMITTED", "PARTIALLY_FILLED")

# Coarse evidence classes used by declarative ``required_evidence`` entries.
# Unknown fine-grained kinds map to themselves so workflows may also require
# a concrete kind directly.
EVIDENCE_KIND_CLASSES = {
    "market_quote": "market",
    "market_snapshot": "market",
    "news_document": "news",
    "earnings_calendar": "earnings",
    "macro_calendar_rule": "macro",
    "options_context": "options",
    "account_snapshot": "portfolio",
    "position_snapshot": "portfolio",
    "backtest_run": "backtest",
    "report": "report",
    "signal": "signal",
    "strategy_run": "runtime",
    "order_intent": "orders",
    "budget_policy": "risk",
}


class WorkflowError(RuntimeError):
    """Structural workflow failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ToolUnavailableError(WorkflowError):
    """A backing data service is unavailable; the step's on_failure decides."""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        aware = _as_utc(value)
        return aware.isoformat() if aware else None
    return str(value)


def _evidence(kind: str, ref: Any, *, url: str | None = None, published_at: Any = None, source: str | None = None) -> dict:
    return {
        "kind": kind,
        "ref": str(ref),
        "url": url,
        "published_at": _iso(published_at),
        "source": source,
    }


@dataclass
class WorkflowContext:
    db: Session
    user: User
    inputs: dict[str, Any]
    manifest: SkillManifest
    now: datetime
    skill_run_id: str | None = None
    results: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    status: str  # completed | degraded | failed
    output: dict[str, Any]
    steps: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    degraded_steps: list[str]
    error: dict[str, Any] | None
    started_at: str
    latency_ms: int
    usage: dict[str, Any]

    def evidence_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "latency_ms": self.latency_ms,
            "steps": self.steps,
            "evidence_refs": self.evidence_refs,
            "degraded_steps": self.degraded_steps,
            "error": self.error,
            "output": self.output,
        }


# ---------------------------------------------------------------------------
# Workflow definition loading & validation
# ---------------------------------------------------------------------------


def load_workflow_definition(content_bundle: dict[str, str] | None, template_ref: str | None) -> dict[str, Any]:
    if not template_ref:
        raise WorkflowError("SKILL_WORKFLOW_NOT_FOUND", "Skill manifest declares no workflow_template_ref")
    raw = (content_bundle or {}).get(template_ref)
    if raw is None:
        raise WorkflowError("SKILL_WORKFLOW_NOT_FOUND", f"workflow bundle entry is missing: {template_ref}")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise WorkflowError("SKILL_WORKFLOW_INVALID", f"workflow YAML is invalid: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list) or not parsed["steps"]:
        raise WorkflowError("SKILL_WORKFLOW_INVALID", "workflow requires a non-empty steps list")
    seen: set[str] = set()
    for step in parsed["steps"]:
        if not isinstance(step, dict):
            raise WorkflowError("SKILL_WORKFLOW_INVALID", "each workflow step must be a mapping")
        step_id = step.get("id")
        tool = step.get("tool")
        if not isinstance(step_id, str) or not step_id or step_id in seen:
            raise WorkflowError("SKILL_WORKFLOW_INVALID", "workflow steps require unique string ids")
        if not isinstance(tool, str) or not tool:
            raise WorkflowError("SKILL_WORKFLOW_INVALID", f"step {step_id} requires a tool name")
        seen.add(step_id)
        for field_name in ("inputs_from", "required_evidence"):
            value = step.get(field_name, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise WorkflowError("SKILL_WORKFLOW_INVALID", f"step {step_id}.{field_name} must be a list of strings")
        if step.get("on_failure", "abort") not in STEP_ON_FAILURE:
            raise WorkflowError("SKILL_WORKFLOW_INVALID", f"step {step_id}.on_failure must be one of {STEP_ON_FAILURE}")
    unknown_tools = [step["tool"] for step in parsed["steps"] if step["tool"] not in TOOL_REGISTRY]
    if unknown_tools:
        raise WorkflowError("SKILL_WORKFLOW_INVALID", f"unknown workflow tools: {sorted(set(unknown_tools))}")
    _topological_order(list(parsed["steps"]))  # surfaces cycles and unknown dependencies at load time
    return parsed


def _topological_order(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {step["id"]: step for step in steps}
    ordered: list[dict[str, Any]] = []
    done: set[str] = set()
    remaining = list(steps)
    while remaining:
        progressed = False
        for step in list(remaining):
            deps = step.get("inputs_from", [])
            unknown = [dep for dep in deps if dep not in by_id]
            if unknown:
                raise WorkflowError("SKILL_WORKFLOW_INVALID", f"step {step['id']} depends on unknown steps: {unknown}")
            if all(dep in done for dep in deps):
                ordered.append(step)
                done.add(step["id"])
                remaining.remove(step)
                progressed = True
        if not progressed:
            raise WorkflowError("SKILL_WORKFLOW_INVALID", "workflow steps contain a dependency cycle")
    return ordered


def _evidence_classes(evidence: list[dict[str, Any]]) -> set[str]:
    classes: set[str] = set()
    for entry in evidence:
        kind = str(entry.get("kind") or "")
        if kind:
            classes.add(EVIDENCE_KIND_CLASSES.get(kind, kind))
    return classes


def _resolve_output(mapping: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, spec in mapping.items():
        if not isinstance(spec, dict) or "from" not in spec:
            output[key] = spec
            continue
        value: Any = (results.get(str(spec["from"])) or {}).get("output") or {}
        for part in str(spec.get("path") or "").split("."):
            if not part:
                continue
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = None
                break
        if value is None and "default" in spec:
            value = spec["default"]
        output[key] = value
    return output


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def run_workflow(
    db: Session,
    *,
    user: User,
    manifest: SkillManifest,
    workflow_def: dict[str, Any],
    inputs: dict[str, Any],
    skill_run: Any | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> WorkflowResult:
    """Execute a validated declarative workflow DAG in dependency order."""
    steps = _topological_order(list(workflow_def.get("steps") or []))
    timeout = float(manifest.runtime.timeout_seconds)
    official = manifest.scope == "official"
    started = clock()
    started_at = _iso(utcnow())
    ctx = WorkflowContext(
        db=db,
        user=user,
        inputs=inputs or {},
        manifest=manifest,
        now=utcnow(),
        skill_run_id=getattr(skill_run, "id", None),
    )
    records: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    degraded: list[str] = []
    error: dict[str, Any] | None = None
    halted = False
    for step in steps:
        if halted:
            records.append({
                "id": step["id"], "tool": step["tool"], "status": "skipped",
                "started_at": None, "latency_ms": 0, "evidence_refs": [],
                "error": {"code": "SKIPPED", "message": "workflow halted before this step"},
            })
            ctx.results[step["id"]] = {"output": {}, "evidence": [], "status": "skipped"}
            continue
        if clock() - started > timeout:
            halted = True
            error = {"code": "SKILL_WORKFLOW_TIMEOUT", "message": f"workflow exceeded the {int(timeout)}s runtime limit"}
            records.append({
                "id": step["id"], "tool": step["tool"], "status": "skipped",
                "started_at": None, "latency_ms": 0, "evidence_refs": [], "error": error,
            })
            ctx.results[step["id"]] = {"output": {}, "evidence": [], "status": "skipped"}
            continue
        tool_name = step["tool"]
        record: dict[str, Any] = {
            "id": step["id"], "tool": tool_name, "status": "running",
            "started_at": _iso(utcnow()), "latency_ms": 0, "evidence_refs": [], "error": None,
        }
        step_started = clock()
        dep_ids = list(step.get("inputs_from", []))
        deps = [(dep_id, ctx.results[dep_id]) for dep_id in dep_ids]
        dep_evidence = [entry for _, dep in deps for entry in dep["evidence"]]
        missing_evidence = sorted(set(step.get("required_evidence", [])) - _evidence_classes(dep_evidence))
        failure: Exception | None = None
        if tool_name in NEVER_IMPORTED_TOOLS:
            failure = WorkflowError("SKILL_TOOL_DENIED", f"{tool_name} may never be imported or executed by a Skill")
        elif tool_name in POLICY_TOOL_NAMES and tool_name not in manifest.tool_allowlist:
            failure = WorkflowError("SKILL_TOOL_DENIED", f"{tool_name} is not in the Skill tool_allowlist")
        elif tool_name not in POLICY_TOOL_NAMES and not official:
            failure = WorkflowError("SKILL_TOOL_DENIED", f"{tool_name} is reserved for reviewed official workflows")
        elif missing_evidence and not manifest.evidence.allow_insufficient_evidence_result:
            failure = WorkflowError("INSUFFICIENT_EVIDENCE", f"missing required evidence: {', '.join(missing_evidence)}")
        if failure is None:
            try:
                result = TOOL_REGISTRY[tool_name](ctx, step.get("args") or {}, deps)
                record["evidence_refs"] = list(result.get("evidence") or [])
                record["status"] = "ok"
                ctx.results[step["id"]] = {
                    "output": result.get("output") or {},
                    "evidence": record["evidence_refs"],
                    "status": "ok",
                }
            except Exception as exc:  # tool failures follow the step's on_failure policy
                failure = exc
        if failure is not None:
            code = getattr(failure, "code", None) or "STEP_FAILED"
            record["error"] = {"code": code, "message": str(failure)[:500]}
            ctx.results[step["id"]] = {"output": {}, "evidence": [], "status": "failed"}
            if step.get("on_failure", "abort") == "degrade":
                record["status"] = "degraded"
                degraded.append(step["id"])
            else:
                record["status"] = "failed"
                halted = True
                error = record["error"]
        elif missing_evidence:
            # Insufficient evidence is never fatal for skills that allow it:
            # the step still ran over real stored data, but the run is marked
            # degraded instead of presenting a partial picture as complete.
            record["status"] = "degraded"
            record["error"] = {"code": "INSUFFICIENT_EVIDENCE", "message": f"missing required evidence: {', '.join(missing_evidence)}"}
            degraded.append(step["id"])
            ctx.results[step["id"]]["status"] = "degraded"
        record["latency_ms"] = int((clock() - step_started) * 1000)
        records.append(record)
        evidence_refs.extend(record["evidence_refs"])
    failed = halted
    status = "failed" if failed else ("degraded" if degraded else "completed")
    output = {} if failed else _resolve_output(workflow_def.get("output") or {}, ctx.results)
    latency_ms = int((clock() - started) * 1000)
    usage = {
        "credits_estimated": manifest.runtime.max_credits_per_run,
        "steps_total": len(steps),
        "steps_ok": sum(1 for record in records if record["status"] == "ok"),
        "steps_degraded": degraded,
        "latency_ms": latency_ms,
        "timeout_seconds": int(timeout),
    }
    result = WorkflowResult(
        status=status,
        output=output,
        steps=records,
        evidence_refs=evidence_refs,
        degraded_steps=degraded,
        error=error,
        started_at=started_at or "",
        latency_ms=latency_ms,
        usage=usage,
    )
    if skill_run is not None:
        skill_run.evidence_json = {**(getattr(skill_run, "evidence_json", None) or {}), "workflow": result.evidence_payload()}
    return result


# ---------------------------------------------------------------------------
# Tool registry: read-only adapters over existing services / stored data.
# Tools receive (ctx, args, deps) and return {"output": dict, "evidence": [...]}.
# apps.api services are imported lazily to keep the module import graph light
# and to keep tests free to monkeypatch the underlying services.
# ---------------------------------------------------------------------------


def _tool_get_market_quote(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    assets = [str(item).upper() for item in (args.get("assets") or ctx.inputs.get("assets") or ["BTC", "ETH"])]
    rows = (
        ctx.db.query(MarketQuoteRecord)
        .filter(MarketQuoteRecord.base_asset.in_(assets))
        .order_by(MarketQuoteRecord.fetched_at.desc())
        .limit(200)
        .all()
    )
    latest: dict[str, MarketQuoteRecord] = {}
    for row in rows:
        key = str(row.base_asset or "").upper()
        if key and key not in latest:
            latest[key] = row
    quotes: list[dict] = []
    evidence: list[dict] = []
    for asset, row in sorted(latest.items()):
        observed = _as_utc(row.source_timestamp) or _as_utc(row.fetched_at)
        quotes.append({
            "symbol": asset,
            "price": float(row.price) if row.price is not None else None,
            "change_24h_pct": float(row.change_24h_pct) if row.change_24h_pct is not None else None,
            "provider": row.provider,
            "timestamp": _iso(observed),
        })
        evidence.append(_evidence("market_quote", row.id, url=(row.provenance_json or {}).get("source_url"), published_at=observed, source=row.provider))
    as_of = max((quote["timestamp"] for quote in quotes if quote["timestamp"]), default=None)
    return {"output": {"quotes": quotes, "as_of": as_of or _iso(ctx.now), "degraded": not quotes}, "evidence": evidence}


def _tool_get_recent_news(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    limit = int(args.get("limit") or ctx.inputs.get("limit") or 10)
    docs = (
        ctx.db.query(NormalizedDocument)
        .order_by(NormalizedDocument.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    items: list[dict] = []
    evidence: list[dict] = []
    for doc in docs:
        published = _as_utc(doc.published_at) or _as_utc(doc.created_at)
        items.append({
            "title": doc.title,
            "url": doc.url,
            "provider": doc.provider,
            "published_at": _iso(published),
            "symbols": list(doc.symbols or []),
        })
        evidence.append(_evidence("news_document", doc.id, url=doc.url, published_at=published, source=doc.provider))
    return {"output": {"items": items, "as_of": _iso(ctx.now), "degraded": not items}, "evidence": evidence}


def _event_evidence(item: dict) -> list[dict]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    provider = source.get("provider") or item.get("source_provider")
    entries: list[dict] = []
    for entry in item.get("evidence") or []:
        entries.append({
            "kind": entry.get("kind"),
            "ref": entry.get("ref"),
            "url": entry.get("url") or source.get("url"),
            "published_at": _iso(entry.get("published_at")),
            "source": provider,
        })
    return entries


def _research_tool(fn: Callable[[WorkflowContext, dict], dict], list_keys: tuple[str, ...]) -> Callable:
    def _run(ctx: WorkflowContext, args: dict, deps: list) -> dict:
        payload = fn(ctx, args)
        evidence: list[dict] = []
        for key in list_keys:
            for item in payload.get(key) or []:
                evidence.extend(_event_evidence(item))
        return {"output": payload, "evidence": evidence}

    return _run


def _tool_research_overnight(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services import research_event_service

    since_hours = int(args.get("since_hours") or ctx.inputs.get("since_hours") or 14)
    return _research_tool(lambda c, a: research_event_service.get_overnight(c.db, c.user, since_hours=since_hours), ("events",))(ctx, args, deps)


def _tool_research_today(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services import research_event_service

    locale = str(ctx.inputs.get("locale") or "en")
    return _research_tool(lambda c, a: research_event_service.get_today(c.db, c.user, locale=locale), ("overnight_events",))(ctx, args, deps)


def _tool_research_upcoming(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services import research_event_service

    days = int(args.get("days") or ctx.inputs.get("days") or 14)
    return _research_tool(lambda c, a: research_event_service.get_upcoming_events(c.db, days=days), ("events",))(ctx, args, deps)


def _tool_research_opportunities(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services import research_event_service

    locale = str(ctx.inputs.get("locale") or "en")
    payload = research_event_service.get_opportunities(ctx.db, ctx.user, locale=locale)
    evidence: list[dict] = []
    for key in ("earnings", "price_moves"):
        for item in payload.get(key) or []:
            evidence.extend(_event_evidence(item))
    for item in payload.get("long_gamma") or []:
        evidence.append(_evidence("options_context", item.get("instrument") or "unknown", url=item.get("source_url"), published_at=payload.get("as_of"), source="deribit_public"))
    return {"output": payload, "evidence": evidence}


def _tool_research_portfolio_impact(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services import research_event_service

    payload = research_event_service.get_portfolio_impact(ctx.db, ctx.user)
    evidence = [
        _evidence("market_event", item.get("event_id"), published_at=item.get("computed_at"), source="research_pipeline")
        for item in payload.get("impacts") or []
        if item.get("event_id")
    ]
    return {"output": payload, "evidence": evidence}


def _tool_get_account_snapshot(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services.portfolio_service import portfolio_context

    context = portfolio_context(ctx.db, ctx.user.id, detailed=True)
    evidence: list[dict] = []
    for account in context.get("accounts") or []:
        evidence.append(_evidence("account_snapshot", account.get("id"), published_at=account.get("as_of"), source=account.get("provider")))
    for holding in context.get("top_holdings") or []:
        evidence.append(_evidence("position_snapshot", holding.get("symbol"), published_at=context.get("data_as_of"), source="portfolio_sync"))
    return {"output": context, "evidence": evidence}


def _tool_confirmed_earnings(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    """Upcoming CONFIRMED earnings only — estimated cadence entries are never emitted."""
    from apps.api.services import research_event_service

    days = int(args.get("days") or ctx.inputs.get("days") or 14)
    horizon = ctx.now + timedelta(days=max(1, days))
    rows = (
        ctx.db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type == "earnings_confirmed",
            MarketEvent.source_published_at.isnot(None),
            MarketEvent.source_published_at >= ctx.now - timedelta(hours=1),
            MarketEvent.source_published_at <= horizon,
        )
        .order_by(MarketEvent.source_published_at.asc())
        .limit(100)
        .all()
    )
    events: list[dict] = []
    evidence: list[dict] = []
    for row in rows:
        serialized = research_event_service.serialize_event(row, now=ctx.now)
        events.append(serialized)
        for entry in row.evidence_json or []:
            if entry.get("kind") != "earnings_calendar":
                continue
            evidence.append(_evidence("earnings_calendar", entry.get("ref"), url=entry.get("url"), published_at=entry.get("published_at"), source=row.source_provider))
    return {"output": {"events": events, "count": len(events), "as_of": _iso(ctx.now), "confirmation": "confirmed_only"}, "evidence": evidence}


def _tool_map_holdings(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services.portfolio_service import portfolio_context

    event_symbols: set[str] = set()
    for _, dep in deps:
        for event in (dep.get("output") or {}).get("events") or []:
            event_symbols.update(str(symbol).upper() for symbol in (event.get("assets") or []))
    context = portfolio_context(ctx.db, ctx.user.id, detailed=True)
    holdings = {str(item.get("symbol") or "").upper() for item in (context.get("top_holdings") or []) if item.get("symbol")}
    watchlist = {
        str(row.asset).upper()
        for row in ctx.db.query(Alert.asset).filter(Alert.user_id == ctx.user.id).distinct().all()
    }
    mapped = sorted(symbol for symbol in event_symbols if symbol in holdings or symbol in watchlist)
    evidence: list[dict] = []
    if context.get("connected"):
        evidence.append(_evidence("account_snapshot", ",".join(context.get("portfolio_ids") or []), published_at=context.get("data_as_of"), source="portfolio_sync"))
    return {
        "output": {
            "mapped_assets": mapped,
            "holdings": sorted(holdings),
            "watchlist": sorted(watchlist),
            "portfolio_connected": bool(context.get("connected")),
        },
        "evidence": evidence,
    }


def _tool_get_options_context(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    """Read-only Deribit long-gamma scan. Degraded chains degrade the step; no
    healthy chain at all makes the tool unavailable (never fabricates)."""
    from apps.api.services import options_service
    from packages.options.long_gamma import discover_long_gamma

    currencies = [str(item).upper() for item in (args.get("currencies") or ctx.inputs.get("currencies") or ["BTC", "ETH"])]
    limit = max(1, min(int(args.get("limit") or ctx.inputs.get("limit") or 10), 25))
    candidates: list[dict] = []
    health: dict[str, dict] = {}
    fetched_at: list[str] = []
    evidence: list[dict] = []
    for currency in currencies:
        try:
            chain = options_service.get_option_chain(currency)
        except Exception as exc:
            health[currency] = {"status": "unavailable", "error": str(exc)[:200]}
            continue
        if not isinstance(chain, dict) or chain.get("status") != "HEALTHY":
            health[currency] = {"status": "degraded", "error": (chain.get("error") if isinstance(chain, dict) else None) or "chain not healthy"}
            continue
        health[currency] = {"status": "ok", "error": None}
        if chain.get("fetched_at"):
            fetched_at.append(str(chain["fetched_at"]))
        evidence.append(_evidence("options_context", f"deribit:{currency}", url=chain.get("source_url"), published_at=chain.get("fetched_at"), source=chain.get("provider") or "deribit_public"))
        for item in discover_long_gamma(chain.get("instruments") or [], limit=limit):
            greeks = item.get("greeks") or {}
            candidates.append({
                "instrument": item.get("instrument"),
                "currency": currency,
                "option_type": item.get("option_type"),
                "expiry": item.get("expiry"),
                "days_to_expiry": item.get("days_to_expiry"),
                "strike": item.get("strike"),
                "gamma": float(greeks.get("gamma") or 0.0),
                "theta": float(greeks.get("theta") or 0.0),
                "spread_pct": item.get("spread_pct"),
                "open_interest": item.get("open_interest"),
                "mark_iv": item.get("mark_iv"),
                "research_score": item.get("research_score"),
                "rationale": list(item.get("rationale") or []),
                "timestamp": item.get("timestamp") or chain.get("fetched_at"),
                "source": chain.get("provider") or "deribit_public",
                "source_url": chain.get("source_url"),
                "execution_enabled": False,
            })
    if not any(entry["status"] == "ok" for entry in health.values()):
        raise ToolUnavailableError("DERIBIT_UNAVAILABLE", "Deribit public options context is unavailable for all configured currencies")
    candidates.sort(key=lambda item: item.get("research_score") or 0, reverse=True)
    return {
        "output": {"candidates": candidates[:limit], "as_of": max(fetched_at) if fetched_at else _iso(ctx.now), "health": health},
        "evidence": evidence,
    }


def _tool_rank_candidates(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    limit = max(1, min(int(args.get("limit") or ctx.inputs.get("limit") or 10), 25))
    candidates: list[dict] = []
    as_of = None
    evidence: list[dict] = []
    for _, dep in deps:
        output = dep.get("output") or {}
        candidates.extend(output.get("candidates") or [])
        as_of = as_of or output.get("as_of")
        evidence.extend(dep.get("evidence") or [])
    ranked = sorted(candidates, key=lambda item: item.get("research_score") or 0, reverse=True)[:limit]
    for index, item in enumerate(ranked):
        item["rank"] = index + 1
    return {"output": {"candidates": ranked, "as_of": as_of or _iso(ctx.now)}, "evidence": evidence}


def _tool_signal_scan(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services.signal_service import serialize_signal

    limit = max(1, min(int(args.get("limit") or ctx.inputs.get("limit") or 10), 50))
    rows = ctx.db.query(Signal).order_by(Signal.created_at.desc()).limit(limit).all()
    signals = [serialize_signal(row) for row in rows]
    evidence = [_evidence("signal", row.id, published_at=row.created_at, source="signal_engine") for row in rows]
    as_of = max((_iso(row.created_at) for row in rows), default=None)
    return {"output": {"signals": signals, "as_of": as_of or _iso(ctx.now), "degraded": not signals}, "evidence": evidence}


def _tool_merge_opportunities(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    limit = max(1, min(int(args.get("limit") or ctx.inputs.get("limit") or 10), 50))
    merged: dict[tuple[str, str], dict] = {}
    sources: list[dict] = []
    for dep_id, dep in deps:
        output = dep.get("output") or {}
        sources.append({"name": dep_id, "status": dep.get("status") or "unknown", "as_of": output.get("as_of")})
        for item in output.get("long_gamma") or []:
            key = ("long_gamma", str(item.get("instrument")))
            merged.setdefault(key, {"type": "long_gamma", "title": item.get("instrument"), "score": item.get("research_score"), "provenance": {"source": "deribit_public", "url": item.get("source_url"), "as_of": output.get("as_of")}})
        for item in output.get("candidates") or []:
            key = ("long_gamma", str(item.get("instrument")))
            merged.setdefault(key, {"type": "long_gamma", "title": item.get("instrument"), "score": item.get("research_score"), "provenance": {"source": item.get("source"), "url": item.get("source_url"), "as_of": item.get("timestamp")}})
        for key_name, type_name in (("earnings", "earnings"), ("price_moves", "price_move"), ("events", "research_event")):
            for item in output.get(key_name) or []:
                source = item.get("source") if isinstance(item.get("source"), dict) else {}
                key = (type_name, str(item.get("title")))
                merged.setdefault(key, {"type": type_name, "title": item.get("title"), "score": item.get("confidence"), "provenance": {"source": source.get("provider"), "url": source.get("url"), "as_of": source.get("published_at")}})
        for item in output.get("signals") or []:
            key = ("signal", f"{item.get('asset')}:{item.get('signal_type')}")
            merged.setdefault(key, {"type": "signal", "title": f"{item.get('asset')} {item.get('direction')}", "score": item.get("confidence"), "provenance": {"source": "signal_engine", "url": None, "as_of": item.get("created_at")}})
    opportunities = sorted(merged.values(), key=lambda item: item.get("score") or 0, reverse=True)[:limit]
    evidence = [entry for _, dep in deps for entry in (dep.get("evidence") or [])]
    return {"output": {"opportunities": opportunities, "sources": sources, "as_of": _iso(ctx.now)}, "evidence": evidence}


def _tool_validate_backtest_spec(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from packages.backtest.strategy_spec import parse_spec

    raw = ctx.inputs.get("spec")
    if not isinstance(raw, dict) or not raw:
        raise WorkflowError("BACKTEST_SPEC_INVALID", "inputs.spec must be a non-empty strategy specification object")
    payload = {
        "name": raw.get("name") or "Workflow research backtest",
        "mode": raw.get("mode", "daily"),
        "signal": raw.get("signal", "momentum"),
        "assets": raw.get("assets") or ["BTC"],
        "fast_window": int(raw.get("fast_window", 12)),
        "slow_window": int(raw.get("slow_window", 26)),
        "entry_threshold": float(raw.get("entry_threshold", 0)),
        "exit_threshold": float(raw.get("exit_threshold", 0)),
        "long_short": bool(raw.get("long_short", False)),
        "max_position": float(raw.get("max_position", 1.0)),
        "fee_bps": float(raw.get("fee_bps", 10)),
        "thesis": raw.get("thesis", ""),
    }
    try:
        spec = parse_spec(payload).model_dump()
    except Exception as exc:
        raise WorkflowError("BACKTEST_SPEC_INVALID", str(exc)[:300]) from exc
    return {"output": {"spec": spec}, "evidence": []}


def _tool_run_nautilus_backtest(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    """Validate → enqueue async backtest (run_id) → poll status once."""
    spec = None
    for _, dep in deps:
        candidate = (dep.get("output") or {}).get("spec")
        if candidate:
            spec = candidate
    if not spec:
        raise WorkflowError("BACKTEST_SPEC_INVALID", "no validated strategy spec from upstream steps")
    window_days = int(ctx.inputs.get("window_days") or 365 * 3)
    try:
        from apps.api.services.unified_backtest_service import create_unified_run

        row = create_unified_run(
            ctx.db,
            ctx.user.id,
            spec,
            window_days=window_days,
            idempotency_key=f"skill:{ctx.manifest.slug}:{ctx.skill_run_id}" if ctx.skill_run_id else None,
            context_meta={"skill": ctx.manifest.slug, "skill_run_id": ctx.skill_run_id},
        )
    except Exception as exc:
        raise ToolUnavailableError("BACKTEST_SERVICE_UNAVAILABLE", str(exc)[:300]) from exc
    dispatched = False
    try:
        from apps.api.redis_client import get_redis

        get_redis().ping()
        from packages.workers.tasks import execute_unified_backtest

        execute_unified_backtest.delay(row.id)
        dispatched = True
    except Exception:
        from apps.api.config import get_settings

        if get_settings().app_environment.lower() == "production":
            raise ToolUnavailableError("BACKTEST_SERVICE_UNAVAILABLE", "backtest queue is temporarily unavailable")
    if not dispatched:
        try:
            from apps.api.services.unified_backtest_service import execute_unified_run

            execute_unified_run(ctx.db, row.id)
        except Exception as exc:
            raise ToolUnavailableError("BACKTEST_SERVICE_UNAVAILABLE", str(exc)[:300]) from exc
    row = ctx.db.get(BacktestRun, row.id)
    status = row.status if row else "unknown"
    metrics = ((row.result_json or {}).get("metrics") or None) if row and status == "completed" else None
    evidence = [_evidence("backtest_run", row.id, published_at=row.created_at, source=row.engine)] if row else []
    return {
        "output": {
            "run_id": row.id if row else None,
            "status": status,
            "metrics": metrics,
            "engine": row.engine if row else None,
            "dispatched": dispatched,
            "credits_reserved": row.credits_reserved if row else 0,
        },
        "evidence": evidence,
    }


def _tool_render_report(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    from apps.api.services.report_service import create_typed_daily_report

    report_type = str(args.get("report_type") or ctx.inputs.get("report_type") or "week_ahead_events")
    language = str(ctx.inputs.get("locale") or "en")
    report = create_typed_daily_report(ctx.db, ctx.user.id, report_type, language, local_date=ctx.now.date(), scheduled=True)
    return {
        "output": {
            "report_id": report.id,
            "title": report.title,
            "report_type": report.report_type,
            "content_markdown": report.content_markdown,
        },
        "evidence": [_evidence("report", report.id, published_at=report.created_at, source="report_service")],
    }


_DISCLAIMERS = {
    "en": "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.",
    "zh": "使用该服务用户自行承担风险，提供本服务的主体概不负责AI生成所有责任。",
}


def _tool_compose_markdown(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    """Deterministic bilingual composition over step evidence only.

    No model calls: phrasing is fixed templates; every rendered fact comes from
    upstream step outputs with source timestamps and citations attached.
    """
    style = str(args.get("style") or "brief")
    locale = str(ctx.inputs.get("locale") or "en").lower()
    zh = locale.startswith("zh")
    events: list[dict] = []
    impacts: list[dict] = []
    gaps: list[str] = []
    portfolio: dict | None = None
    as_of = None
    for _, dep in deps:
        output = dep.get("output") or {}
        as_of = as_of or output.get("as_of")
        for key in ("events", "overnight_events"):
            events.extend(output.get(key) or [])
        impacts.extend(output.get("impacts") or [])
        if "total_nav" in output or "connected" in output:
            portfolio = output
        gaps.extend(str(item) for item in (output.get("missing_data") or []))
        health = output.get("health")
        if isinstance(health, dict):
            overall = health.get("overall")
            if overall and overall != "ok":
                gaps.append(f"research health: {overall}")
            for name, info in (health.get("sources") or {}).items():
                if isinstance(info, dict) and info.get("status") not in (None, "ok"):
                    gaps.append(f"source {name}: {info.get('status')}")
            for name, info in health.items():
                if name in {"sources", "overall"}:
                    continue
                if isinstance(info, dict) and info.get("status") not in (None, "ok"):
                    gaps.append(f"source {name}: {info.get('status')}")
    for item in events:
        gaps.extend(str(gap) for gap in (item.get("evidence_gaps") or []))
    deduped_gaps = list(dict.fromkeys(gaps))
    citations: list[dict] = []
    seen_urls: set[str] = set()
    for item in events:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        url = source.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        citations.append({"title": item.get("title"), "url": url, "published_at": source.get("published_at")})
    as_of = as_of or _iso(ctx.now)
    lines: list[str] = []
    if style == "review":
        lines.append("# 投资组合影响审查" if zh else "# Portfolio Impact Review")
        if portfolio and portfolio.get("connected"):
            nav = portfolio.get("total_nav")
            daily = portfolio.get("daily_change")
            lines.append(
                (f"_净值 NAV: {nav} | 24h 变动: {daily} | 数据截至 {portfolio.get('data_as_of')}_")
                if zh
                else (f"_NAV: {nav} | 24h change: {daily} | data as of {portfolio.get('data_as_of')}_")
            )
        else:
            lines.append("_未连接投资组合账户，以下为基于已存证据的通用审查。_" if zh else "_No portfolio account connected; review is based on stored evidence only._")
        lines.append("")
        lines.append("## 组合影响" if zh else "## Portfolio impacts")
        if impacts:
            for item in impacts:
                title = item.get("event_title") or item.get("event_type") or "research event"
                lines.append(f"- **{item.get('symbol')}**: {title} — {item.get('direction') or 'unknown'} (confidence {item.get('confidence')})")
        else:
            lines.append("- 当前没有与你的持仓映射的研究事件。" if zh else "- No stored research events currently map to your holdings.")
    else:
        lines.append("# 隔夜市场简报" if zh else "# Overnight Market Brief")
        lines.append((f"_数据截至 {as_of}（UTC）。仅基于已存证据生成。_") if zh else (f"_Data as of {as_of} (UTC). Built only from stored, cited evidence._"))
        lines.append("")
        lines.append("## 隔夜动态" if zh else "## What happened")
        if events:
            for item in events:
                source = item.get("source") if isinstance(item.get("source"), dict) else {}
                url = source.get("url")
                published = source.get("published_at")
                summary = (item.get("summary") or "").strip()
                link = f" ([source]({url}), {published})" if url else (f" ({published})" if published else "")
                lines.append(f"- **{item.get('title')}** — {summary}{link}")
        else:
            lines.append("- 窗口内没有已存的市场事件。" if zh else "- No stored market events in the window.")
    lines.append("")
    lines.append("## 证据缺口" if zh else "## Evidence gaps")
    if deduped_gaps:
        lines.extend(f"- {gap}" for gap in deduped_gaps)
    else:
        lines.append("- 无：所需证据类别齐全。" if zh else "- None: all required evidence classes were present.")
    if citations:
        lines.append("")
        lines.append("## 引用来源" if zh else "## Citations")
        for citation in citations:
            lines.append(f"- [{citation['title']}]({citation['url']}) ({citation.get('published_at')})")
    lines.append("")
    lines.append(_DISCLAIMERS["zh"] if zh else _DISCLAIMERS["en"])
    markdown = "\n".join(lines)
    return {
        "output": {"markdown": markdown, "citations": citations, "gaps": deduped_gaps, "locale": "zh" if zh else "en"},
        "evidence": [entry for _, dep in deps for entry in (dep.get("evidence") or [])],
    }


def _tool_get_strategy_status(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    rows = (
        ctx.db.query(StrategyRun)
        .filter(StrategyRun.user_id == ctx.user.id)
        .order_by(StrategyRun.updated_at.desc())
        .limit(50)
        .all()
    )
    by_status: dict[str, int] = {}
    errors: list[dict] = []
    evidence: list[dict] = []
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        if row.error_code or row.status not in ("PENDING", "RUNNING", "STOPPED", "COMPLETED"):
            errors.append({
                "run_id": row.id,
                "status": row.status,
                "error_code": row.error_code,
                "updated_at": _iso(row.updated_at),
            })
    for row in rows[:10]:
        evidence.append(_evidence("strategy_run", row.id, published_at=row.updated_at, source="nautilus_runtime"))
    return {"output": {"run_count": len(rows), "by_status": by_status, "recent_errors": errors, "as_of": _iso(ctx.now)}, "evidence": evidence}


def _tool_get_open_orders(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    rows = (
        ctx.db.query(OrderIntent)
        .filter(OrderIntent.user_id == ctx.user.id, OrderIntent.status.in_(OPEN_ORDER_INTENT_STATUSES))
        .order_by(OrderIntent.created_at.desc())
        .limit(20)
        .all()
    )
    open_orders = [
        {
            "id": row.id,
            "instrument": row.instrument,
            "venue": row.venue,
            "direction": row.direction,
            "quantity": row.quantity,
            "status": row.status,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]
    evidence = [_evidence("order_intent", row.id, published_at=row.created_at, source=row.venue) for row in rows]
    return {"output": {"open_orders": open_orders, "count": len(open_orders)}, "evidence": evidence}


def _tool_risk_state(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    policies = ctx.db.query(CreditBudgetPolicy).filter(CreditBudgetPolicy.user_id == ctx.user.id).all()
    paused = [
        {"automation_key": row.automation_key, "pause_reason": row.pause_reason}
        for row in policies
        if row.paused
    ]
    stale_accounts: list[dict] = []
    accounts = ctx.db.query(TradingAccount).filter_by(user_id=ctx.user.id, account_type="READ_ONLY", status="ACTIVE").all()
    evidence: list[dict] = []
    for account in accounts:
        snapshot = (
            ctx.db.query(AccountSnapshot)
            .filter(AccountSnapshot.user_id == ctx.user.id, AccountSnapshot.account_id == account.id)
            .order_by(AccountSnapshot.captured_at.desc())
            .first()
        )
        if snapshot is None:
            stale_accounts.append({"account": account.name, "reason": "no_snapshot"})
        elif snapshot.stale:
            stale_accounts.append({"account": account.name, "reason": "stale", "captured_at": _iso(snapshot.captured_at)})
        if snapshot is not None:
            evidence.append(_evidence("account_snapshot", account.id, published_at=snapshot.captured_at, source=account.venue))
    evidence.extend(_evidence("budget_policy", row.id, published_at=row.updated_at, source="billing") for row in policies if row.paused)
    return {
        "output": {"paused_budgets": paused, "stale_accounts": stale_accounts, "budget_count": len(policies)},
        "evidence": evidence,
    }


def _tool_detect_anomalies(ctx: WorkflowContext, args: dict, deps: list) -> dict:
    findings: list[dict] = []
    for dep_id, dep in deps:
        output = dep.get("output") or {}
        if dep.get("status") == "degraded":
            findings.append({"severity": "warning", "title": f"{dep_id} data is degraded; monitor coverage is partial"})
        for error in output.get("recent_errors") or []:
            findings.append({
                "severity": "high",
                "title": f"Strategy run {error.get('run_id')} ended {error.get('status')} ({error.get('error_code') or 'no error code'})",
            })
        if output.get("count"):
            findings.append({"severity": "info", "title": f"{output['count']} open order intent(s) pending review"})
        for paused in output.get("paused_budgets") or []:
            findings.append({"severity": "warning", "title": f"Automation budget paused: {paused.get('automation_key')} ({paused.get('pause_reason') or 'no reason recorded'})"})
        for stale in output.get("stale_accounts") or []:
            findings.append({"severity": "warning", "title": f"Portfolio account {stale.get('account')}: {stale.get('reason')}"})
    status = "attention" if any(item["severity"] in {"high", "warning"} for item in findings) else "ok"
    if not findings:
        findings.append({"severity": "info", "title": "No runtime, order, or risk anomalies detected"})
    evidence = [entry for _, dep in deps for entry in (dep.get("evidence") or [])]
    return {"output": {"status": status, "findings": findings, "checked_at": _iso(ctx.now)}, "evidence": evidence}


TOOL_REGISTRY: dict[str, Callable[[WorkflowContext, dict, list], dict]] = {
    "get_market_quote": _tool_get_market_quote,
    "get_recent_news": _tool_get_recent_news,
    "research_overnight": _tool_research_overnight,
    "research_today": _tool_research_today,
    "research_upcoming": _tool_research_upcoming,
    "research_opportunities": _tool_research_opportunities,
    "research_portfolio_impact": _tool_research_portfolio_impact,
    "get_account_snapshot": _tool_get_account_snapshot,
    "confirmed_earnings": _tool_confirmed_earnings,
    "map_holdings": _tool_map_holdings,
    "get_options_context": _tool_get_options_context,
    "rank_candidates": _tool_rank_candidates,
    "signal_scan": _tool_signal_scan,
    "merge_opportunities": _tool_merge_opportunities,
    "validate_backtest_spec": _tool_validate_backtest_spec,
    "run_nautilus_backtest": _tool_run_nautilus_backtest,
    "render_report": _tool_render_report,
    "compose_markdown": _tool_compose_markdown,
    "get_strategy_status": _tool_get_strategy_status,
    "get_open_orders": _tool_get_open_orders,
    "risk_state": _tool_risk_state,
    "detect_anomalies": _tool_detect_anomalies,
}

# Runtime state transitions are performed only by the audited control plane;
# the workflow registry must never expose them to Skill content.
_FORBIDDEN_TOOLS = set(TOOL_REGISTRY) & NEVER_IMPORTED_TOOLS
if _FORBIDDEN_TOOLS:
    raise RuntimeError(f"workflow registry must never contain: {sorted(_FORBIDDEN_TOOLS)}")
