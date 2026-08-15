"""MemoryService: the only sanctioned writer of user memory.

All operations are user-scoped (multi-tenant isolated), audit-recorded,
idempotent where possible, and policy-checked. Models and Harness cannot
call the database directly; they can only produce MemoryProposals.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from packages.database.models import (
    AgentConversation,
    ConversationMemorySummary,
    MemoryAuditRecord,
    MemoryProposal,
    MemoryScopeSetting,
    UserMemory,
    utcnow,
)
from packages.memory.policy import (
    MEMORY_NAMESPACES,
    MemoryDecision,
    MemoryPolicy,
    content_hash,
    redact_secrets,
)


def _trace() -> str:
    return str(uuid.uuid4())


# Hard bounds for conversation summary fields: any caller-supplied text is
# recursively scanned for secrets and truncated, and id arrays are capped.
_MAX_SUMMARY_TEXT_CHARS = 2000
_MAX_SUMMARY_LIST_ITEMS = 50
_MAX_MESSAGE_IDS = 200
_MAX_ID_CHARS = 200


def _redact_text_recursive(value: Any) -> Any:
    if isinstance(value, str):
        text = redact_secrets(value)
        if len(text) > _MAX_SUMMARY_TEXT_CHARS:
            text = text[:_MAX_SUMMARY_TEXT_CHARS] + "…"
        return text
    if isinstance(value, dict):
        return {str(key): _redact_text_recursive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_text_recursive(item) for item in value]
    return value


def _sanitize_text_list(values: Any) -> list:
    if not isinstance(values, (list, tuple)):
        return []
    return _redact_text_recursive(list(values))[:_MAX_SUMMARY_LIST_ITEMS]


def _sanitize_id_list(values: Any) -> list:
    if not isinstance(values, (list, tuple)):
        return []
    ids: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        ids.append(value[:_MAX_ID_CHARS])
        if len(ids) >= _MAX_MESSAGE_IDS:
            break
    return ids


def _audit(
    db: Session,
    *,
    user_id: str,
    action: str,
    target_type: str = "memory",
    target_id: str | None = None,
    namespace: str | None = None,
    detail: dict[str, Any] | None = None,
    actor: str = "system",
    trace_id: str | None = None,
) -> MemoryAuditRecord:
    row = MemoryAuditRecord(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        namespace=namespace,
        detail_json=detail or {},
        actor=actor,
        trace_id=trace_id or _trace(),
    )
    db.add(row)
    return row


class MemoryService:
    def __init__(self, *, auto_accept_low_risk: bool = True, summary_ttl_days: int = 30) -> None:
        self.policy = MemoryPolicy(auto_accept_low_risk=auto_accept_low_risk)
        self.summary_ttl_days = summary_ttl_days

    # ------------------------------------------------------------------ #
    # Proposals and consent
    # ------------------------------------------------------------------ #
    def propose(
        self,
        db: Session,
        *,
        user_id: str,
        namespace: str,
        kind: str,
        content: dict[str, Any],
        proposed_by: str = "model",
        source_type: str = "model_proposal",
        source_id: str | None = None,
        source_run_id: str | None = None,
        proposed_ttl_seconds: int | None = None,
        idempotency_key: str | None = None,
    ) -> MemoryProposal:
        key = idempotency_key or f"memory-proposal:{user_id}:{namespace}:{content_hash(content)}"
        existing = (
            db.query(MemoryProposal).filter(MemoryProposal.idempotency_key == key).first()
        )
        if existing is not None:
            return existing  # idempotent

        decision = self.policy.decide(
            namespace=namespace,
            kind=kind,
            content=content,
            proposed_ttl_seconds=proposed_ttl_seconds,
        )
        clean_content = {k: (redact_secrets(v) if isinstance(v, str) else v) for k, v in content.items()}
        proposal = MemoryProposal(
            user_id=user_id,
            proposed_by=proposed_by,
            source_run_id=source_run_id,
            namespace=namespace,
            kind=kind,
            content_json=clean_content,
            source_type=source_type,
            source_id=source_id,
            source_hash=content_hash(content),
            proposed_ttl_seconds=proposed_ttl_seconds,
            sensitivity="high" if decision.action == "reject" else "low",
            status="rejected" if decision.action == "reject" else (
                "auto_accepted" if decision.action == "auto_accept" else "pending"
            ),
            decision_reason=decision.reason,
            idempotency_key=key,
            expires_at=(
                utcnow() + timedelta(seconds=decision.ttl_seconds)
                if decision.ttl_seconds is not None
                else None
            ),
        )
        db.add(proposal)
        db.flush()
        _audit(
            db,
            user_id=user_id,
            action="propose",
            target_type="memory_proposal",
            target_id=proposal.id,
            namespace=namespace,
            detail={"kind": kind, "decision": proposal.status, "reason": decision.reason},
            actor=proposed_by,
        )

        if decision.action == "auto_accept":
            memory = self._write_memory(db, proposal, decision, actor="auto_accept")
            proposal.status = "auto_accepted"
            proposal.memory_id = memory.id
            proposal.decided_at = utcnow()
        db.commit()
        return proposal

    def approve_proposal(self, db: Session, *, user_id: str, proposal_id: str) -> UserMemory:
        proposal = (
            db.query(MemoryProposal)
            .filter(MemoryProposal.id == proposal_id, MemoryProposal.user_id == user_id)
            .first()
        )
        if proposal is None:
            raise LookupError("memory proposal not found")
        if proposal.status in {"rejected", "user_approved", "auto_accepted"}:
            if proposal.memory_id:
                memory = db.query(UserMemory).filter(UserMemory.id == proposal.memory_id).first()
                if memory:
                    return memory
        if proposal.status == "rejected":
            raise ValueError("proposal was rejected by policy and cannot be approved")

        decision = MemoryDecision("auto_accept", "user approved", proposal.proposed_ttl_seconds)
        memory = self._write_memory(db, proposal, decision, actor="user_confirmed")
        proposal.status = "user_approved"
        proposal.memory_id = memory.id
        proposal.decided_by_user_id = user_id
        proposal.decided_at = utcnow()
        _audit(
            db,
            user_id=user_id,
            action="approve",
            target_type="memory_proposal",
            target_id=proposal.id,
            namespace=proposal.namespace,
            detail={"memory_id": memory.id},
            actor="user",
        )
        db.commit()
        return memory

    def reject_proposal(self, db: Session, *, user_id: str, proposal_id: str, reason: str = "") -> None:
        proposal = (
            db.query(MemoryProposal)
            .filter(MemoryProposal.id == proposal_id, MemoryProposal.user_id == user_id)
            .first()
        )
        if proposal is None:
            raise LookupError("memory proposal not found")
        proposal.status = "rejected"
        proposal.decision_reason = reason or "rejected by user"
        proposal.decided_by_user_id = user_id
        proposal.decided_at = utcnow()
        _audit(
            db,
            user_id=user_id,
            action="reject",
            target_type="memory_proposal",
            target_id=proposal.id,
            namespace=proposal.namespace,
            detail={"reason": proposal.decision_reason},
            actor="user",
        )
        db.commit()

    def _write_memory(
        self, db: Session, proposal: MemoryProposal, decision: MemoryDecision, *, actor: str
    ) -> UserMemory:
        expires_at = (
            utcnow() + timedelta(seconds=decision.ttl_seconds)
            if decision.ttl_seconds is not None
            else None
        )
        memory = UserMemory(
            user_id=proposal.user_id,
            namespace=proposal.namespace,
            kind=proposal.kind,
            content_json=proposal.content_json,
            source_type=proposal.source_type,
            source_id=proposal.source_id,
            source_hash=proposal.source_hash,
            created_by="deterministic" if proposal.proposed_by == "deterministic" else proposal.proposed_by,
            consent_scope=proposal.namespace if proposal.namespace != "portfolio" else "none",
            expires_at=expires_at,
        )
        db.add(memory)
        db.flush()
        _audit(
            db,
            user_id=proposal.user_id,
            action="write",
            target_type="memory",
            target_id=memory.id,
            namespace=proposal.namespace,
            detail={"kind": proposal.kind, "created_by": memory.created_by},
            actor=actor,
        )
        return memory

    # ------------------------------------------------------------------ #
    # Retrieval (always user-scoped, consent-scoped, freshness-filtered)
    # ------------------------------------------------------------------ #
    def retrieve_for_context(
        self,
        db: Session,
        *,
        user_id: str,
        namespaces: tuple[str, ...] = ("chat", "research"),
        limit: int = 8,
    ) -> list[UserMemory]:
        """Model-context retrieval. The MemoryScopeSetting check is
        NON-BYPASSABLE by design: there is deliberately no parameter to skip
        it. User-facing listing (not model context) uses ``list_memories``.
        """
        if limit > 32:
            limit = 32
        # A disabled scope is a hard opt-out: its memories are never
        # injected into model context, regardless of caller arguments.
        disabled = {
            row.scope
            for row in db.query(MemoryScopeSetting)
            .filter(MemoryScopeSetting.user_id == user_id)
            .all()
            if not row.enabled
        }
        effective_namespaces = tuple(n for n in namespaces if n not in disabled)
        if not effective_namespaces:
            return []
        now = utcnow()
        query = (
            db.query(UserMemory)
            .filter(
                UserMemory.user_id == user_id,
                UserMemory.namespace.in_(effective_namespaces),
                UserMemory.status == "active",
            )
            .filter((UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > now))
        )
        rows = query.order_by(UserMemory.salience.desc(), UserMemory.updated_at.desc()).limit(limit).all()
        for row in rows:
            row.last_used_at = now
        _audit(
            db,
            user_id=user_id,
            action="read",
            target_type="memory",
            namespace=",".join(effective_namespaces),
            detail={"count": len(rows)},
            actor="system",
        )
        return rows

    def list_memories(
        self, db: Session, *, user_id: str, namespace: str | None = None, include_inactive: bool = False
    ) -> list[UserMemory]:
        """User-facing listing (settings/export UI). NEVER use this to build
        model context: only ``retrieve_for_context`` may feed the model, and
        that path cannot bypass scope opt-outs."""
        query = db.query(UserMemory).filter(UserMemory.user_id == user_id)
        if namespace is not None:
            query = query.filter(UserMemory.namespace == namespace)
        if not include_inactive:
            query = query.filter(UserMemory.status == "active")
        return query.order_by(UserMemory.updated_at.desc()).all()

    def list_proposals(
        self, db: Session, *, user_id: str, status: str | None = None
    ) -> list[MemoryProposal]:
        query = db.query(MemoryProposal).filter(MemoryProposal.user_id == user_id)
        if status is not None:
            query = query.filter(MemoryProposal.status == status)
        return query.order_by(MemoryProposal.created_at.desc()).all()

    # ------------------------------------------------------------------ #
    # User management operations
    # ------------------------------------------------------------------ #
    def update_memory(
        self, db: Session, *, user_id: str, memory_id: str, content: dict[str, Any]
    ) -> UserMemory:
        memory = (
            db.query(UserMemory)
            .filter(UserMemory.id == memory_id, UserMemory.user_id == user_id)
            .first()
        )
        if memory is None:
            raise LookupError("memory not found")
        decision = self.policy.decide(
            namespace=memory.namespace,
            kind=memory.kind,
            content=content,
            proposed_ttl_seconds=None,
        )
        if decision.action == "reject":
            raise ValueError(f"update rejected by policy: {decision.reason}")
        memory.content_json = {k: (redact_secrets(v) if isinstance(v, str) else v) for k, v in content.items()}
        memory.source_hash = content_hash(content)
        memory.source_type = "user_confirmed"
        memory.created_by = "user_confirmed"
        _audit(
            db,
            user_id=user_id,
            action="update",
            target_type="memory",
            target_id=memory.id,
            namespace=memory.namespace,
            actor="user",
        )
        db.commit()
        return memory

    def delete_memory(self, db: Session, *, user_id: str, memory_id: str) -> None:
        memory = (
            db.query(UserMemory)
            .filter(UserMemory.id == memory_id, UserMemory.user_id == user_id)
            .first()
        )
        if memory is None:
            return
        namespace = memory.namespace
        db.delete(memory)
        _audit(
            db,
            user_id=user_id,
            action="delete",
            target_type="memory",
            target_id=memory_id,
            namespace=namespace,
            actor="user",
        )
        db.commit()

    def clear_namespace(self, db: Session, *, user_id: str, namespace: str) -> int:
        rows = (
            db.query(UserMemory)
            .filter(UserMemory.user_id == user_id, UserMemory.namespace == namespace)
            .all()
        )
        for row in rows:
            db.delete(row)
        _audit(
            db,
            user_id=user_id,
            action="clear_namespace",
            target_type="memory",
            namespace=namespace,
            detail={"count": len(rows)},
            actor="user",
        )
        db.commit()
        return len(rows)

    def export_memories(self, db: Session, *, user_id: str) -> dict[str, Any]:
        rows = self.list_memories(db, user_id=user_id, include_inactive=True)
        payload = {
            "user_id": user_id,
            "exported_at": utcnow().isoformat(),
            "memories": [
                {
                    "id": r.id,
                    "namespace": r.namespace,
                    "kind": r.kind,
                    "content": r.content_json,
                    "created_by": r.created_by,
                    "consent_scope": r.consent_scope,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                }
                for r in rows
            ],
        }
        _audit(
            db,
            user_id=user_id,
            action="export",
            target_type="memory",
            detail={"count": len(rows)},
            actor="user",
        )
        db.commit()
        return payload

    def set_scope_enabled(
        self, db: Session, *, user_id: str, scope: str, enabled: bool
    ) -> MemoryScopeSetting:
        if scope not in MEMORY_NAMESPACES:
            raise ValueError(f"unknown memory scope: {scope}")
        row = (
            db.query(MemoryScopeSetting)
            .filter(MemoryScopeSetting.user_id == user_id, MemoryScopeSetting.scope == scope)
            .first()
        )
        if row is None:
            row = MemoryScopeSetting(user_id=user_id, scope=scope, enabled=enabled, changed_by="user")
            db.add(row)
        else:
            row.enabled = enabled
        _audit(
            db,
            user_id=user_id,
            action="disable_scope" if not enabled else "write",
            target_type="memory_scope",
            target_id=row.id,
            namespace=scope,
            detail={"enabled": enabled},
            actor="user",
        )
        db.commit()
        return row

    def expire_stale(self, db: Session, *, user_id: str) -> int:
        now = utcnow()
        rows = (
            db.query(UserMemory)
            .filter(
                UserMemory.user_id == user_id,
                UserMemory.status == "active",
                UserMemory.expires_at.isnot(None),
                UserMemory.expires_at <= now,
            )
            .all()
        )
        for row in rows:
            row.status = "expired"
        if rows:
            db.commit()
        return len(rows)

    # ------------------------------------------------------------------ #
    # Short-term conversation memory
    # ------------------------------------------------------------------ #
    def save_conversation_summary(
        self,
        db: Session,
        *,
        user_id: str,
        conversation_id: str,
        summary_text: str,
        source_message_ids: list[str],
        recent_message_ids: list[str],
        goals: list[str] | None = None,
        known_facts: list[str] | None = None,
        used_evidence: list[str] | None = None,
        open_questions: list[str] | None = None,
        user_preferences: list[str] | None = None,
        token_estimate: int = 0,
    ) -> ConversationMemorySummary:
        # Ownership check first: the conversation must belong to this user.
        # The two FKs alone cannot guarantee (conversation, user) coherence.
        conversation = (
            db.query(AgentConversation)
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )
        if conversation is None:
            raise LookupError("conversation not found or not owned by this user")

        previous = (
            db.query(ConversationMemorySummary)
            .filter(
                ConversationMemorySummary.conversation_id == conversation_id,
                ConversationMemorySummary.user_id == user_id,
                ConversationMemorySummary.superseded_by.is_(None),
            )
            .order_by(ConversationMemorySummary.version.desc())
            .first()
        )
        next_version = (previous.version + 1) if previous else 1
        row = ConversationMemorySummary(
            user_id=user_id,
            conversation_id=conversation_id,
            version=next_version,
            summary_text=redact_secrets(summary_text)[:_MAX_SUMMARY_TEXT_CHARS],
            summary_token_estimate=max(0, min(token_estimate, 1500)),
            recent_message_ids_json=_sanitize_id_list(recent_message_ids),
            source_message_ids_json=_sanitize_id_list(source_message_ids),
            goals_json=_sanitize_text_list(goals),
            known_facts_json=_sanitize_text_list(known_facts),
            used_evidence_json=_sanitize_text_list(used_evidence),
            open_questions_json=_sanitize_text_list(open_questions),
            user_preferences_json=_sanitize_text_list(user_preferences),
            expires_at=utcnow() + timedelta(days=self.summary_ttl_days),
        )
        db.add(row)
        db.flush()
        if previous is not None:
            previous.superseded_by = row.id
        _audit(
            db,
            user_id=user_id,
            action="write",
            target_type="conversation_summary",
            target_id=row.id,
            namespace="chat",
            detail={"version": row.version},
            actor="system",
        )
        db.commit()
        return row

    def active_conversation_summary(
        self, db: Session, *, conversation_id: str, user_id: str
    ) -> ConversationMemorySummary | None:
        """Return the active summary for a conversation owned by ``user_id``."""
        now = utcnow()
        return (
            db.query(ConversationMemorySummary)
            .filter(
                ConversationMemorySummary.conversation_id == conversation_id,
                ConversationMemorySummary.user_id == user_id,
                ConversationMemorySummary.superseded_by.is_(None),
            )
            .filter(
                (ConversationMemorySummary.expires_at.is_(None))
                | (ConversationMemorySummary.expires_at > now)
            )
            .order_by(ConversationMemorySummary.version.desc())
            .first()
        )
