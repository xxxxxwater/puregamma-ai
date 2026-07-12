from apps.api.services import agent_service
from apps.api.services.credit_service import refund_credits
from packages.database.models import AgentMessage, AgentRun, CreditLedger


def test_agent_run_consumes_credits_and_filters_unentitled_sources(db, normal_user):
    conversation = agent_service.create_conversation(db, normal_user)

    run = agent_service.start_run(
        db,
        normal_user,
        conversation,
        "Review BTC news",
        context={"data_sources": ["rss", "x-twitter"], "skills": ["news_research"]},
    )

    db.refresh(normal_user)
    user_message = db.get(AgentMessage, run.user_message_id)
    assert run.credit_cost == 3
    assert normal_user.credit_balance == 27
    assert user_message.context_json["data_sources"] == ["rss"]
    assert user_message.context_json["denied_data_sources"] == [
        {"provider": "x-twitter", "reason": "plan_required"}
    ]
    ledger = db.query(CreditLedger).filter_by(idempotency_key=f"agent-charge:{run.id}").one()
    assert ledger.credits_delta == -3


def test_agent_refund_is_idempotent(db, normal_user):
    initial_balance = normal_user.credit_balance
    key = "agent-refund:test-run"

    first = refund_credits(db, normal_user.id, "agent_chat_basic", 2, idempotency_key=key)
    second = refund_credits(db, normal_user.id, "agent_chat_basic", 2, idempotency_key=key)
    db.commit()

    db.refresh(normal_user)
    assert first.id == second.id
    assert normal_user.credit_balance == initial_balance + 2
    assert db.query(CreditLedger).filter_by(idempotency_key=key).count() == 1


def test_agent_concurrency_limit_uses_plan_capability(db, normal_user):
    db.add(
        AgentRun(
            user_id=normal_user.id,
            conversation_id="active-conversation",
            user_message_id="active-user-message",
            assistant_message_id="active-assistant-message",
            model="mock",
            trace_id="active-trace",
            status="running",
        )
    )
    db.commit()

    try:
        agent_service.assert_quota(db, normal_user)
    except agent_service.AgentLimitError as exc:
        assert str(exc) == "AGENT_CONCURRENT_LIMIT_REACHED"
    else:
        raise AssertionError("Free plan concurrent Agent limit should be enforced")
