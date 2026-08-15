"""State machine, isolation, tool contract, and mock adapter tests for the
DeepSeek Harness research foundation (Phase 1)."""

from __future__ import annotations

import pytest

from packages.database.models import HarnessResearchRun, HarnessRunStateTransition
from packages.harness import (
    ALLOWED_GATEWAY_TOOLS,
    ALLOWED_TRANSITIONS,
    DENIED_HARNESS_CAPABILITIES,
    TERMINAL_STATES,
    MockHarnessAdapter,
    assert_tool_allowed,
    compute_input_hash,
    transition_run,
)
from packages.harness.state_machine import IllegalStateTransition


def _make_run(db, user, status: str = "queued", **overrides) -> HarnessResearchRun:
    values = dict(
        user_id=user.id,
        status=status,
        requested_goal_summary="test deep research",
        input_hash=compute_input_hash("test deep research"),
        harness_version="test-harness-0",
        runtime_version="test-runtime-0",
        cordis_config_hash="sha256:test",
        plugin_lock_hash="sha256:test",
        idempotency_key="run-key",
        trace_id="trace-1",
    )
    values.update(overrides)
    run = HarnessResearchRun(**values)
    db.add(run)
    db.commit()
    return run


def test_happy_path_state_machine(db, normal_user):
    run = _make_run(db, normal_user)
    for status in ("preparing", "running", "validating", "completed"):
        changed = transition_run(db, run, status)
        db.commit()
        assert changed is True
        assert run.status == status
    transitions = (
        db.query(HarnessRunStateTransition)
        .filter(HarnessRunStateTransition.research_run_id == run.id)
        .all()
    )
    assert [t.from_status for t in transitions] == ["queued", "preparing", "running", "validating"]
    assert [t.to_status for t in transitions] == ["preparing", "running", "validating", "completed"]
    assert run.started_at is not None
    assert run.completed_at is not None


def test_transition_is_idempotent(db, normal_user):
    run = _make_run(db, normal_user)
    transition_run(db, run, "preparing")
    db.commit()
    changed = transition_run(db, run, "preparing")
    assert changed is False
    count = (
        db.query(HarnessRunStateTransition)
        .filter(HarnessRunStateTransition.research_run_id == run.id)
        .count()
    )
    assert count == 1


def test_illegal_transition_raises(db, normal_user):
    run = _make_run(db, normal_user)
    with pytest.raises(IllegalStateTransition):
        transition_run(db, run, "running")  # queued -> running is not allowed
    with pytest.raises(IllegalStateTransition):
        transition_run(db, run, "completed")  # queued -> completed is not allowed
    transition_run(db, run, "preparing")
    transition_run(db, run, "running")
    transition_run(db, run, "validating")
    transition_run(db, run, "completed")  # terminal
    db.commit()
    with pytest.raises(IllegalStateTransition):
        transition_run(db, run, "running")  # terminal states are immutable


def test_terminal_states_have_no_exits():
    for terminal in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_cancel_and_timeout_record_flags(db, normal_user):
    run = _make_run(db, normal_user)
    transition_run(db, run, "preparing")
    transition_run(db, run, "running")
    db.commit()
    transition_run(db, run, "canceled", actor="user", reason="user requested")
    db.commit()
    assert run.canceled_at is not None
    assert run.completed_at is not None

    run2 = _make_run(db, normal_user, idempotency_key="run-key-2", trace_id="trace-2")
    transition_run(db, run2, "timed_out", actor="orchestrator")
    db.commit()
    assert run2.timeout_at is not None


def test_tenant_isolation(db, normal_user, pro_user):
    run_a = _make_run(db, normal_user)
    run_b = _make_run(db, pro_user, idempotency_key="run-key-b", trace_id="trace-b")
    assert (
        db.query(HarnessResearchRun)
        .filter(HarnessResearchRun.user_id == normal_user.id)
        .count()
        == 1
    )
    assert run_a.id != run_b.id
    # A user-scoped query never surfaces the other user's run.
    visible = db.query(HarnessResearchRun).filter(HarnessResearchRun.user_id == normal_user.id).all()
    assert [r.id for r in visible] == [run_a.id]


def test_tool_contract_rejects_denied_capabilities():
    for tool in ("shell", "bash", "filesystem", "editor", "url_fetch", "sql", "docker", "env_read", "order"):
        with pytest.raises(ValueError):
            assert_tool_allowed(tool)
    # Unrecognized tools fail closed too.
    with pytest.raises(ValueError):
        assert_tool_allowed("arbitrary_tool")
    # Every allowlisted gateway tool passes.
    for tool in ALLOWED_GATEWAY_TOOLS:
        assert assert_tool_allowed(tool) == tool


def test_denied_list_covers_order_and_account_actions():
    for forbidden in (
        "order",
        "strategy_mutation",
        "risk_policy_mutation",
        "mandate_mutation",
        "kill_switch",
        "account_connect",
        "withdraw",
        "transfer",
        "payment",
        "direct_message",
    ):
        assert forbidden in DENIED_HARNESS_CAPABILITIES


def test_mock_adapter_is_deterministic_and_restricted():
    adapter = MockHarnessAdapter()
    goal = "Analyze BTC ETF flows vs on-chain liquidation this week"
    evidence = {
        "items": [
            {"source_id": "s1", "source_url": "https://example.test/1", "source_timestamp": "2026-08-14T00:00:00Z"},
            {"source_id": "s2", "source_url": "https://example.test/2", "source_timestamp": "2026-08-14T01:00:00Z"},
        ]
    }
    allowed = ALLOWED_GATEWAY_TOOLS
    adapter.start_run(
        run_id="r1",
        user_id="u1",
        goal_summary=goal,
        evidence=evidence,
        allowed_tools=allowed,
        budget_credits=150,
        timeout_seconds=720,
        session_id="sess-1",
    )
    first = adapter.poll_result("r1")
    second = adapter.poll_result("r1")
    assert first is not None and second is not None
    assert first.status == "completed"
    assert first.usage == second.usage
    assert first.markdown == second.markdown
    # Every mock tool trace stays inside the gateway allowlist.
    for trace in first.tool_traces:
        assert trace.tool_name in ALLOWED_GATEWAY_TOOLS
    # Citations come from the frozen evidence only.
    assert {c["source_id"] for c in first.citations} == {"s1", "s2"}


def test_mock_adapter_cancel():
    adapter = MockHarnessAdapter()
    adapter.start_run(
        run_id="r1",
        user_id="u1",
        goal_summary="goal",
        evidence={},
        allowed_tools=ALLOWED_GATEWAY_TOOLS,
        budget_credits=10,
        timeout_seconds=60,
        session_id="sess-1",
    )
    adapter.cancel_run("r1")
    result = adapter.poll_result("r1")
    assert result is not None
    assert result.status == "canceled"


def test_mock_adapter_cannot_widen_tool_contract():
    adapter = MockHarnessAdapter()
    with pytest.raises(ValueError):
        adapter.start_run(
            run_id="r1",
            user_id="u1",
            goal_summary="goal",
            evidence={},
            allowed_tools=("shell",),
            budget_credits=10,
            timeout_seconds=60,
            session_id="sess-1",
        )


def test_input_hash_is_deterministic():
    a = compute_input_hash("goal", evidence_snapshot_hash="h1", skill_version="1.0.0")
    b = compute_input_hash("goal", evidence_snapshot_hash="h1", skill_version="1.0.0")
    c = compute_input_hash("goal2", evidence_snapshot_hash="h1", skill_version="1.0.0")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_extra_allowlist_can_only_narrow():
    # A run-scoped allowlist may narrow the global set...
    assert assert_tool_allowed("run_backtest", extra_allowlist=("run_backtest",)) == "run_backtest"
    # ...and may exclude global tools...
    with pytest.raises(ValueError):
        assert_tool_allowed("get_market_series", extra_allowlist=("run_backtest",))
    # ...but it can NEVER introduce a tool outside the global allowlist.
    with pytest.raises(ValueError):
        assert_tool_allowed("some_new_tool", extra_allowlist=("some_new_tool",))
    with pytest.raises(ValueError):
        assert_tool_allowed("run_backtest", extra_allowlist=("run_backtest", "some_new_tool"))


def test_concurrent_transition_applies_once(db, normal_user):
    """Two racing transitions on the same run must yield exactly one effective
    state change and one audit row (conditional-update guard)."""
    run = _make_run(db, normal_user)
    assert transition_run(db, run, "preparing") is True
    db.commit()

    # Simulate a stale worker holding the pre-transition state.
    stale = HarnessResearchRun(
        id=run.id,
        user_id=normal_user.id,
        status="queued",
        trace_id=run.trace_id,
    )
    assert transition_run(db, stale, "failed") is False
    db.commit()

    # The authoritative state is unchanged and only one transition exists.
    fresh = db.query(HarnessResearchRun).filter(HarnessResearchRun.id == run.id).one()
    assert fresh.status == "preparing"
    count = (
        db.query(HarnessRunStateTransition)
        .filter(HarnessRunStateTransition.research_run_id == run.id)
        .count()
    )
    assert count == 1


def test_evidence_snapshot_is_immutable(db, normal_user):
    from packages.database.models import EvidenceSnapshot

    snap = EvidenceSnapshot(
        user_id=normal_user.id,
        content_hash="hash-immutable-test",
        normalized_evidence_json={"items": []},
    )
    db.add(snap)
    db.commit()
    snap.normalized_evidence_json = {"items": [1]}
    with pytest.raises(RuntimeError, match="immutable"):
        db.commit()


def test_evidence_snapshot_shared_scope_dedupes_null_owner(db):
    """Two shared-market snapshots (user_id NULL) with the same
    (content_hash, source_scope) must not coexist."""
    from sqlalchemy.exc import IntegrityError

    from packages.database.models import EvidenceSnapshot

    db.add(
        EvidenceSnapshot(
            user_id=None,
            source_scope="shared_market",
            content_hash="shared-hash-1",
            normalized_evidence_json={"items": []},
        )
    )
    db.commit()
    duplicate = EvidenceSnapshot(
        user_id=None,
        source_scope="shared_market",
        content_hash="shared-hash-1",
        normalized_evidence_json={"items": []},
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_evidence_snapshot_user_scoped_unique_rules(db, normal_user, pro_user):
    """Same content may serve different users, but not duplicate for one user
    in one scope."""
    from sqlalchemy.exc import IntegrityError

    from packages.database.models import EvidenceSnapshot

    def add(user_id, scope, content_hash):
        db.add(
            EvidenceSnapshot(
                user_id=user_id,
                source_scope=scope,
                content_hash=content_hash,
                normalized_evidence_json={"items": []},
            )
        )
        db.commit()

    add(normal_user.id, "run", "user-hash-1")
    # Different user, same scope + hash: allowed.
    add(pro_user.id, "run", "user-hash-1")
    # Same user, different scope: allowed.
    add(normal_user.id, "portfolio", "user-hash-1")
    # Same user + scope + hash: rejected.
    db.add(
        EvidenceSnapshot(
            user_id=normal_user.id,
            source_scope="run",
            content_hash="user-hash-1",
            normalized_evidence_json={"items": []},
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_strategy_release_spec_is_immutable(db, normal_user):
    from packages.database.models import StrategyRelease, TradingStrategy

    strategy = TradingStrategy(user_id=normal_user.id, name="test strategy")
    db.add(strategy)
    db.commit()
    release = StrategyRelease(
        user_id=normal_user.id,
        strategy_id=strategy.id,
        strategy_version=1,
        spec_json={"signal": "deterministic"},
        spec_hash="spec-hash-1",
    )
    db.add(release)
    db.commit()

    # Spec mutation is blocked...
    release.spec_json = {"signal": "mutated"}
    with pytest.raises(RuntimeError, match="immutable"):
        db.commit()
    db.rollback()

    # ...but the review lifecycle fields remain writable.
    release.review_status = "approved"
    release.review_notes = "reviewed"
    db.commit()
    assert release.review_status == "approved"


def test_trading_mandate_amounts_are_numeric(db, normal_user):
    from sqlalchemy import Numeric

    from packages.database.models import TradingMandate

    for column_name in (
        "max_total_notional",
        "max_per_order_notional",
        "max_position_notional",
        "max_leverage",
        "max_daily_loss",
    ):
        column = TradingMandate.__table__.c[column_name]
        assert isinstance(column.type, Numeric), f"{column_name} must be Numeric, got {column.type}"


def test_auto_trading_live_never_effective_in_phase1(monkeypatch):
    from apps.api.config import Settings

    monkeypatch.setenv("AUTO_TRADING_LIVE_ENABLED", "true")
    monkeypatch.setenv("AUTO_TRADING_DEPLOYMENT_LIVE_APPROVED", "true")
    settings = Settings()
    # Even with both environment flags set (and even with the attribute
    # forced true), Phase 1 never exposes an effective LIVE gate.
    assert settings.auto_trading_live_effective is False
    object.__setattr__(settings, "auto_trading_live_enabled", True)
    assert settings.auto_trading_live_effective is False
