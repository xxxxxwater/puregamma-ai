from __future__ import annotations

from tests.conftest import auth_headers


def test_secretary_reply_is_tenant_isolated_metered_and_idempotent(api_client, db, normal_user, max_user):
    request_id = "secretary-idempotency-0001"
    initial_balance = normal_user.credit_balance
    payload = {"content": "Help me plan today's research.", "locale": "en", "request_id": request_id}

    first = api_client.post("/api/secretary/messages", json=payload, headers=auth_headers(normal_user))
    assert first.status_code == 200
    result = first.json()
    assert result["credits_used"] == 20
    assert result["credit_balance"] == initial_balance - 20

    repeated = api_client.post("/api/secretary/messages", json=payload, headers=auth_headers(normal_user))
    assert repeated.status_code == 200
    assert repeated.json()["assistant_message"]["id"] == result["assistant_message"]["id"]
    db.refresh(normal_user)
    assert normal_user.credit_balance == initial_balance - 20

    owner_state = api_client.get("/api/secretary", headers=auth_headers(normal_user))
    other_state = api_client.get("/api/secretary", headers=auth_headers(max_user))
    assert owner_state.status_code == 200
    assert len(owner_state.json()["messages"]) == 2
    assert other_state.status_code == 200
    assert other_state.json()["messages"] == []


def test_secretary_provider_failure_refunds_reservation(api_client, db, normal_user, monkeypatch):
    from apps.api.routers import secretary

    class FailingProvider:
        def complete(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(secretary, "get_llm_provider", lambda: FailingProvider())
    initial_balance = normal_user.credit_balance
    response = api_client.post(
        "/api/secretary/messages",
        json={"content": "Summarize my day.", "locale": "en", "request_id": "secretary-refund-test-0001"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SECRETARY_MODEL_UNAVAILABLE"
    db.refresh(normal_user)
    assert normal_user.credit_balance == initial_balance
