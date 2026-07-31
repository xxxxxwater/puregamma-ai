from apps.api.services import agent_service
from packages.database.models import AgentRun


def test_agent_daily_limit_is_exposed_and_enforced(db, demo_user):
    state = agent_service.quota_state(db, demo_user)
    assert state["limit"] == 5
    assert state["remaining"] == 5

    for index in range(5):
        db.add(AgentRun(user_id=demo_user.id, conversation_id=f"c-{index}", user_message_id=f"u-{index}", assistant_message_id=f"a-{index}", model="mock", trace_id=f"t-{index}"))
    db.commit()

    try:
        agent_service.assert_quota(db, demo_user)
    except ValueError:
        return
    raise AssertionError("Free Agent daily limit should be enforced")
