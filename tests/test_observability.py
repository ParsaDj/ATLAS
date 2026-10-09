import logging

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.migrations import upgrade_database


TEST_ADMIN_PASSWORD = "atlas-test-admin-password"
TEST_BRIDGE_KEY = "atlas-test-bridge-key-1234567890"


class RecordLogger:
    def __init__(self):
        self.records = []

    def info(self, message, extra):
        self.records.append({"message": message, **extra})


def observable_client(database_url):
    upgrade_database(database_url)
    log = RecordLogger()
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password=TEST_ADMIN_PASSWORD,
        telemetry_api_key=TEST_BRIDGE_KEY,
        request_log=log,
    )
    return app, log


def test_liveness_readiness_and_request_correlation(database_url):
    app, log = observable_client(database_url)
    with TestClient(app) as client:
        health = client.get("/health", headers={"X-Request-ID": "operator-check-17"})
        assert health.json() == {"status": "ok"}
        assert health.headers["X-Request-ID"] == "operator-check-17"

        ready = client.get("/ready", headers={"X-Request-ID": "invalid request id"})
        assert ready.json() == {"status": "ready"}
        assert ready.headers["X-Request-ID"] != "invalid request id"

    health_record = next(item for item in log.records if item["route"] == "/health")
    assert health_record["message"] == "request.completed"
    assert health_record["request_id"] == "operator-check-17"
    assert health_record["status_code"] == 200
    assert len(health_record["trace_id"]) == 32
    assert TEST_ADMIN_PASSWORD not in repr(log.records)
    assert TEST_BRIDGE_KEY not in repr(log.records)


def test_version_reports_injected_build_provenance(database_url):
    upgrade_database(database_url)
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password=TEST_ADMIN_PASSWORD,
        telemetry_api_key=TEST_BRIDGE_KEY,
        build_sha="0123456789abcdef",
    )
    with TestClient(app) as client:
        response = client.get("/version")
    assert response.json() == {
        "version": "0.1.0",
        "build_sha": "0123456789abcdef",
    }


def test_metrics_use_route_templates_and_report_operational_state(database_url):
    app, _ = observable_client(database_url)
    with TestClient(app) as client:
        headers = {"X-ATLAS-Bridge-Key": TEST_BRIDGE_KEY}
        assert client.get("/api/robots/robot-1", headers=headers).status_code == 200
        assert client.get("/api/robots/missing", headers=headers).status_code == 404
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert 'route="/api/robots/{robot_id}"' in body
    assert 'route="/api/robots/robot-1"' not in body
    assert 'atlas_robots{status="unknown"} 5' in body
    assert "atlas_http_request_duration_seconds" in body
    assert "atlas_http_requests_in_progress 1" in body


def test_json_formatter_does_not_serialize_unapproved_record_fields():
    from apps.api.observability import JsonFormatter

    record = logging.LogRecord(
        "atlas.api.requests", logging.INFO, __file__, 1, "request.completed", (), None
    )
    record.request_id = "req-1"
    record.method = "POST"
    record.route = "/api/telemetry"
    record.status_code = 200
    record.duration_ms = 2.5
    output = JsonFormatter().format(record)

    assert '"request_id":"req-1"' in output
    assert "password" not in output
    assert "telemetry_api_key" not in output
