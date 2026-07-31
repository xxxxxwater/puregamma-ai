from fastapi.testclient import TestClient

from apps.api.main import app


def test_liveness_and_readiness_expose_request_and_dependency_state():
    with TestClient(app) as client:
        health = client.get("/health", headers={"X-Request-ID": "test-request-id"})
        readiness = client.get("/ready")

    assert health.status_code == 200
    assert health.headers["X-Request-ID"] == "test-request-id"
    assert health.json() == {"status": "ok", "service": "puregamma-api"}
    assert readiness.status_code == 200
    assert readiness.json()["database"] == "ok"
    assert readiness.json()["redis"] in {"ok", "error"}
