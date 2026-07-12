from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_exposes_dependencies_and_request_id():
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.json()["database"] == "ok"
    assert response.json()["redis"] in {"ok", "error"}
