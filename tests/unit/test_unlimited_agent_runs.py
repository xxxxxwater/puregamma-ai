from apps.api.services import agent_service


def test_agent_daily_limit_is_not_enforced(monkeypatch, db, demo_user):
    monkeypatch.setattr(agent_service, "_quota", lambda _db, _user: (5, 5))

    agent_service.assert_quota(db, demo_user)

    state = agent_service.quota_state(db, demo_user)
    assert state["limit"] is None
    assert state["remaining"] is None
