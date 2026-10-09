from datetime import datetime, timezone

from simulator.failure_demo import execute_demo


def test_failure_demo_stops_at_human_approval_boundary(system):
    client, _, _ = system
    result = execute_demo(
        client,
        run_id="test-draft",
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )

    assert result["mission"]["status"] == "failed"
    assert result["incident"]["type"] == "sensor_failure"
    assert result["incident"]["event_ids"] == ["demo:test-draft:sensor-failed"]
    assert result["investigation"]["confidence"] == "supported"
    assert {citation["id"] for citation in result["investigation"]["citations"]} >= {
        "demo:test-draft:sensor-failed",
        result["mission"]["id"],
        "DOC-SENSOR-001",
    }
    assert result["maintenance_ticket"]["status"] == "draft"


def test_explicit_demo_approval_uses_server_workflow(system):
    client, _, _ = system
    result = execute_demo(
        client,
        run_id="test-approved",
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        approve_maintenance=True,
    )

    assert result["maintenance_ticket"]["status"] == "approved"
    logs = client.get("/api/audit-logs").json()
    ticket_id = result["maintenance_ticket"]["id"]
    assert {log["action"] for log in logs if log["resource_id"] == ticket_id} == {
        "ticket.create",
        "ticket.approve",
    }
