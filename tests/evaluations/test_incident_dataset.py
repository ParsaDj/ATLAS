"""Reproducible 120-case evaluation with expectations kept outside inputs."""
import pytest

from apps.ai_agent.service import investigate


FAULTS = ("low_battery", "sensor_failure", "disconnection")


def cases():
    for index in range(120):
        fault = FAULTS[index % len(FAULTS)]
        event_id = None if fault == "disconnection" else f"event-{index}"
        yield pytest.param(index, fault, event_id, id=f"case-{index:03d}-{fault}")


@pytest.mark.parametrize("index,fault,event_id", list(cases()))
def test_investigation_dataset(index, fault, event_id):
    incident = {
        "id": f"incident-{index}",
        "robot_id": f"robot-{index % 5 + 1}",
        "mission_id": f"mission-{index}",
        "type": fault,
        "event_ids": [event_id] if event_id else [],
    }
    event = {
        "event_id": event_id,
        "battery": 12 if fault == "low_battery" else 80,
        "sensor_status": "failed" if fault == "sensor_failure" else "ok",
    }
    result = investigate(
        incident,
        {"id": incident["mission_id"]},
        [event] if event_id else [],
    )

    # Expected labels are defined here, outside the agent-visible inputs.
    expected_confidence = "limited" if fault == "disconnection" else "supported"
    expected_document = {
        "low_battery": "DOC-BATTERY-001",
        "sensor_failure": "DOC-SENSOR-001",
        "disconnection": "DOC-CONNECTION-001",
    }[fault]
    assert result["confidence"] == expected_confidence
    assert expected_document in {citation["id"] for citation in result["citations"]}
    assert incident["mission_id"] in {
        citation["id"] for citation in result["citations"]
    }
    assert all(tool["tool"] in {
        "get_incident", "get_mission", "list_incident_events", "retrieve_document"
    } for tool in result["tool_trace"])
    assert result["limitations"]
