"""Memory Policy and MemoryService tests: multi-tenant isolation, TTL,
namespace rules, secret rejection, trading-namespace write block, and the
rule that memory is never trading input."""

from __future__ import annotations

from datetime import timedelta

import pytest

from packages.database.models import AgentConversation, UserMemory, utcnow
from packages.memory import (
    MEMORY_NAMESPACES,
    WRITE_DISABLED_NAMESPACES,
    MemoryPolicy,
    MemoryService,
    detect_secrets,
)


def _make_conversation(db, user, conversation_id: str = "conv-1") -> AgentConversation:
    row = AgentConversation(id=conversation_id, user_id=user.id, title="test conversation")
    db.add(row)
    db.commit()
    return row


class TestMemoryPolicy:
    def test_trading_namespace_write_is_rejected(self):
        policy = MemoryPolicy()
        decision = policy.decide(
            namespace="trading",
            kind="watchlist",
            content={"note": "buy BTC"},
            proposed_ttl_seconds=None,
        )
        assert decision.action == "reject"

    def test_unknown_namespace_rejected(self):
        policy = MemoryPolicy()
        decision = policy.decide(
            namespace="orders", kind="x", content={}, proposed_ttl_seconds=None
        )
        assert decision.action == "reject"

    def test_secret_content_is_rejected(self):
        policy = MemoryPolicy()
        for secret in (
            "sk-abcdefghijklmnopqrstuvwxyz1234",
            "pk_live_abcdefghijklmnop",
            "-----BEGIN PRIVATE KEY-----",
            "0x" + "ab" * 32,
            "Bearer eyJhbGciOiJIUzI1NiJ9.abc.def123456789",
            "postgresql://user:pass@host/db",
        ):
            decision = policy.decide(
                namespace="research",
                kind="watchlist",
                content={"note": secret},
                proposed_ttl_seconds=None,
            )
            assert decision.action == "reject", secret[:20]
            assert "secret pattern" in decision.reason

    def test_low_risk_auto_accept_matrix(self):
        policy = MemoryPolicy(auto_accept_low_risk=True)
        for kind, expected in (
            ("language_preference", "auto_accept"),
            ("display_preference", "auto_accept"),
            ("research_task_incomplete", "auto_accept"),
            ("watchlist", "pending"),
            ("deep_research_conclusion_summary", "pending"),
            ("secretary_todo", "pending"),
        ):
            decision = policy.decide(
                namespace="research" if kind != "language_preference" else "chat",
                kind=kind,
                content={"value": "x"},
                proposed_ttl_seconds=None,
            )
            assert decision.action == expected, kind

    def test_auto_accept_can_be_disabled(self):
        policy = MemoryPolicy(auto_accept_low_risk=False)
        decision = policy.decide(
            namespace="chat",
            kind="language_preference",
            content={"value": "zh"},
            proposed_ttl_seconds=None,
        )
        assert decision.action == "pending"

    def test_ttl_defaults(self):
        policy = MemoryPolicy()
        decision = policy.decide(
            namespace="research",
            kind="research_task_incomplete",
            content={"value": "x"},
            proposed_ttl_seconds=None,
        )
        assert decision.ttl_seconds == 30 * 86400
        decision = policy.decide(
            namespace="chat",
            kind="language_preference",
            content={"value": "zh"},
            proposed_ttl_seconds=None,
        )
        assert decision.ttl_seconds is None

    def test_secret_detector_matches_and_redacts(self):
        from packages.memory.policy import redact_secrets

        text = "my key is sk-abcdefghijklmnopqrstuvwxyz1234 ok"
        assert detect_secrets(text)
        assert "sk-abcdefghijklmnop" not in redact_secrets(text)
        assert "[REDACTED]" in redact_secrets(text)


class TestMemoryService:
    def _service(self) -> MemoryService:
        return MemoryService(auto_accept_low_risk=True, summary_ttl_days=30)

    def test_auto_accept_writes_memory_and_audit(self, db, normal_user):
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="chat",
            kind="language_preference",
            content={"value": "中文、简洁"},
        )
        assert proposal.status == "auto_accepted"
        assert proposal.memory_id is not None
        memories = svc.list_memories(db, user_id=normal_user.id)
        assert len(memories) == 1
        assert memories[0].content_json == {"value": "中文、简洁"}

    def test_watchlist_requires_consent(self, db, normal_user):
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="research",
            kind="watchlist",
            content={"symbols": ["BTC", "ETH"]},
        )
        assert proposal.status == "pending"
        assert svc.list_memories(db, user_id=normal_user.id) == []
        memory = svc.approve_proposal(db, user_id=normal_user.id, proposal_id=proposal.id)
        assert memory.namespace == "research"
        assert svc.list_memories(db, user_id=normal_user.id)[0].id == memory.id

    def test_rejected_secret_cannot_be_approved(self, db, normal_user):
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="research",
            kind="watchlist",
            content={"note": "key sk-abcdefghijklmnopqrstuvwxyz1234"},
        )
        assert proposal.status == "rejected"
        with pytest.raises(ValueError):
            svc.approve_proposal(db, user_id=normal_user.id, proposal_id=proposal.id)

    def test_trading_namespace_proposal_is_rejected(self, db, normal_user):
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="trading",
            kind="watchlist",
            content={"note": "nope"},
        )
        assert proposal.status == "rejected"
        assert svc.list_memories(db, user_id=normal_user.id) == []

    def test_multi_tenant_isolation(self, db, normal_user, pro_user):
        svc = self._service()
        svc.propose(
            db,
            user_id=normal_user.id,
            namespace="chat",
            kind="language_preference",
            content={"value": "en"},
        )
        svc.propose(
            db,
            user_id=pro_user.id,
            namespace="chat",
            kind="language_preference",
            content={"value": "zh"},
        )
        a = svc.list_memories(db, user_id=normal_user.id)
        b = svc.list_memories(db, user_id=pro_user.id)
        assert len(a) == 1 and len(b) == 1
        assert a[0].user_id == normal_user.id
        assert b[0].user_id == pro_user.id
        # User A cannot touch user B's memory or proposals.
        with pytest.raises(LookupError):
            svc.approve_proposal(db, user_id=normal_user.id, proposal_id="does-not-exist")
        assert db.query(UserMemory).filter(UserMemory.user_id == normal_user.id).count() == 1
        # Cross-user delete is a no-op and never deletes the other user's row.
        svc.delete_memory(db, user_id=normal_user.id, memory_id=b[0].id)
        assert db.query(UserMemory).filter(UserMemory.user_id == pro_user.id).count() == 1

    def test_expiry_and_retrieval_filters(self, db, normal_user):
        svc = self._service()
        memory = svc.approve_proposal(
            db,
            user_id=normal_user.id,
            proposal_id=svc.propose(
                db,
                user_id=normal_user.id,
                namespace="research",
                kind="watchlist",
                content={"symbols": ["BTC"]},
            ).id,
        )
        rows = svc.retrieve_for_context(db, user_id=normal_user.id, namespaces=("research",))
        assert [r.id for r in rows] == [memory.id]

        # Expire it directly, then retrieval excludes it.
        memory.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        rows = svc.retrieve_for_context(db, user_id=normal_user.id, namespaces=("research",))
        assert rows == []
        assert svc.expire_stale(db, user_id=normal_user.id) == 1
        assert memory.status == "expired"

    def test_update_delete_clear_and_export(self, db, normal_user):
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="research",
            kind="watchlist",
            content={"symbols": ["BTC"]},
        )
        memory = svc.approve_proposal(db, user_id=normal_user.id, proposal_id=proposal.id)
        updated = svc.update_memory(
            db, user_id=normal_user.id, memory_id=memory.id, content={"symbols": ["BTC", "MSTR"]}
        )
        assert updated.content_json["symbols"] == ["BTC", "MSTR"]

        svc.propose(
            db,
            user_id=normal_user.id,
            namespace="research",
            kind="research_task_incomplete",
            content={"value": "unfinished study"},
        )
        assert svc.clear_namespace(db, user_id=normal_user.id, namespace="research") == 2
        exported = svc.export_memories(db, user_id=normal_user.id)
        assert exported["memories"] == []
        assert "exported_at" in exported

    def test_scope_settings(self, db, normal_user):
        svc = self._service()
        row = svc.set_scope_enabled(db, user_id=normal_user.id, scope="trading", enabled=False)
        assert row.enabled is False
        with pytest.raises(ValueError):
            svc.set_scope_enabled(db, user_id=normal_user.id, scope="orders", enabled=True)

    def test_disabled_scope_is_not_retrievable(self, db, normal_user):
        """Turning a scope off must stop memory injection into model context."""
        svc = self._service()
        svc.propose(
            db,
            user_id=normal_user.id,
            namespace="chat",
            kind="language_preference",
            content={"value": "zh"},
        )
        assert len(svc.retrieve_for_context(db, user_id=normal_user.id, namespaces=("chat",))) == 1

        svc.set_scope_enabled(db, user_id=normal_user.id, scope="chat", enabled=False)
        assert svc.retrieve_for_context(db, user_id=normal_user.id, namespaces=("chat",)) == []
        # Other still-enabled scopes keep working.
        svc.propose(
            db,
            user_id=normal_user.id,
            namespace="research",
            kind="research_task_incomplete",
            content={"value": "task"},
        )
        rows = svc.retrieve_for_context(db, user_id=normal_user.id, namespaces=("chat", "research"))
        assert all(r.namespace == "research" for r in rows)

    def test_retrieve_for_context_has_no_bypass_flag(self):
        """No caller may pass a flag that skips the MemoryScopeSetting check."""
        import inspect

        signature = inspect.signature(MemoryService.retrieve_for_context)
        assert "scope_enabled_check" not in signature.parameters
        assert set(signature.parameters) >= {"db", "user_id", "namespaces", "limit"}

    def test_proposal_ttl_uses_policy_decision(self, db, normal_user):
        """A 60-second TTL must produce ~60s expiry, not the 30-day summary TTL."""
        svc = self._service()
        # SQLite returns naive datetimes, so compare in naive UTC.
        before = utcnow().replace(tzinfo=None)
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="chat",
            kind="language_preference",
            content={"value": "zh"},
            proposed_ttl_seconds=60,
        )
        assert proposal.expires_at is not None
        delta = (proposal.expires_at - before).total_seconds()
        assert 55 <= delta <= 65, f"proposal TTL delta={delta}s"
        # The auto-accepted memory row honors the same decision TTL.
        memory = db.query(UserMemory).filter(UserMemory.id == proposal.memory_id).one()
        assert memory.expires_at is not None
        delta_memory = (memory.expires_at - before).total_seconds()
        assert 55 <= delta_memory <= 65, f"memory TTL delta={delta_memory}s"

    def test_conversation_summary_lifecycle(self, db, normal_user):
        svc = self._service()
        _make_conversation(db, normal_user, "conv-1")
        summary = svc.save_conversation_summary(
            db,
            user_id=normal_user.id,
            conversation_id="conv-1",
            summary_text="goal: compare BTC ETF flows with onchain liquidation",
            source_message_ids=["m1", "m2"],
            recent_message_ids=["m1", "m2"],
            goals=["compare ETF vs liquidation"],
            open_questions=["missing CME data"],
        )
        assert summary.version == 1
        v2 = svc.save_conversation_summary(
            db,
            user_id=normal_user.id,
            conversation_id="conv-1",
            summary_text="updated summary",
            source_message_ids=["m3"],
            recent_message_ids=["m3"],
        )
        assert v2.version == 2
        active = svc.active_conversation_summary(db, conversation_id="conv-1", user_id=normal_user.id)
        assert active.id == v2.id

    def test_summary_redacts_secrets(self, db, normal_user):
        svc = self._service()
        _make_conversation(db, normal_user, "conv-1")
        summary = svc.save_conversation_summary(
            db,
            user_id=normal_user.id,
            conversation_id="conv-1",
            summary_text="user key: sk-abcdefghijklmnopqrstuvwxyz1234",
            source_message_ids=["m1"],
            recent_message_ids=["m1"],
        )
        assert "sk-abcdefghijklmnop" not in summary.summary_text
        assert "[REDACTED]" in summary.summary_text

    def test_summary_structured_fields_are_sanitized(self, db, normal_user):
        """Secrets in structured summary fields are redacted and id arrays
        are length/count capped before persistence."""
        import json

        svc = self._service()
        _make_conversation(db, normal_user, "conv-structured")
        summary = svc.save_conversation_summary(
            db,
            user_id=normal_user.id,
            conversation_id="conv-structured",
            summary_text="ok",
            source_message_ids=["m" * 500, 123, ""],
            recent_message_ids=["m1"] * 250,
            goals=["buy BTC with key sk-abcdefghijklmnopqrstuvwxyz1234"],
            known_facts=[{"api_key": "pk_live_abcdefghijklmnop"}],
            used_evidence=[{"url": "postgresql://user:pass@host/db?x=1"}],
            open_questions=["what about Bearer eyJhbGciOiJIUzI1NiJ9.abc.def123456789 ?"],
            user_preferences=["wallet seed 0x" + "ab" * 32],
        )
        serialized = json.dumps(
            {
                "goals": summary.goals_json,
                "known_facts": summary.known_facts_json,
                "used_evidence": summary.used_evidence_json,
                "open_questions": summary.open_questions_json,
                "user_preferences": summary.user_preferences_json,
            }
        )
        for forbidden in ("sk-abcdefghijklmnop", "pk_live_", "postgresql://", "Bearer eyJhbGciOi", "0x" + "ab" * 32):
            assert forbidden not in serialized, forbidden
        assert "[REDACTED]" in serialized
        # ID arrays: non-strings dropped, strings truncated, count capped.
        assert len(summary.source_message_ids_json) == 1
        assert len(summary.source_message_ids_json[0]) == 200
        assert len(summary.recent_message_ids_json) == 200

    def test_conversation_summary_requires_ownership(self, db, normal_user, pro_user):
        """User A cannot write or read user B's conversation summary."""
        svc = self._service()
        conv_b = _make_conversation(db, pro_user, "conv-b")
        with pytest.raises(LookupError):
            svc.save_conversation_summary(
                db,
                user_id=normal_user.id,  # A pretending to own B's conversation
                conversation_id=conv_b.id,
                summary_text="cross-tenant attempt",
                source_message_ids=["m1"],
                recent_message_ids=["m1"],
            )
        # B owns the conversation; A reads nothing from it.
        svc.save_conversation_summary(
            db,
            user_id=pro_user.id,
            conversation_id=conv_b.id,
            summary_text="B's summary",
            source_message_ids=["m1"],
            recent_message_ids=["m1"],
        )
        assert svc.active_conversation_summary(db, conversation_id=conv_b.id, user_id=pro_user.id) is not None
        assert svc.active_conversation_summary(db, conversation_id=conv_b.id, user_id=normal_user.id) is None

    def test_memory_can_never_be_trading_input(self, db, normal_user):
        # Contract: trading namespace cannot hold writes, so no memory can ever
        # feed a mandate/order decision through this service.
        svc = self._service()
        proposal = svc.propose(
            db,
            user_id=normal_user.id,
            namespace="trading",
            kind="strategy_hint",
            content={"note": "should never persist"},
        )
        assert proposal.status == "rejected"
        assert db.query(UserMemory).filter(UserMemory.namespace == "trading").count() == 0
        assert "trading" in WRITE_DISABLED_NAMESPACES
        assert MEMORY_NAMESPACES == {"chat", "secretary", "research", "portfolio", "trading"}
