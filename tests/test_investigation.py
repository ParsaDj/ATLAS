from apps.ai_agent.service import investigate, retrieve_guides
from simulator.fleet import sample


def create_incident(system, robot, *, sensor="ok", battery=80):
    client, clock, _ = system
    created = client.post(
        "/api/missions",
        json={"robot_id": robot, "waypoints": [{"x": 1, "y": 1}]},
    ).json()
    client.post(f"/api/missions/{created['id']}/approve")
    body = sample(robot, created["id"], 0, "investigation", clock[0].isoformat())
    body["sensor_status"] = sensor
    body["battery"] = battery
    client.post("/api/telemetry", json=body)
    incident = client.get("/api/incidents").json()[0]
    return client, created, body, incident


def test_low_battery_investigation_cites_event_mission_and_document(system):
    client, mission, event, incident = create_incident(system, "robot-2", battery=12)
    response = client.post(f"/api/incidents/{incident['id']}/investigate")
    assert response.status_code == 200
    result = response.json()
    assert result["confidence"] == "supported"
    assert "12% battery" in result["finding"]
    assert result["generated_by"] == "atlas-evidence-engine-v1"
    assert {tuple(item.values()) for item in result["citations"]} == {
        ("event", event["event_id"]),
        ("mission", mission["id"]),
        ("document", "DOC-BATTERY-001"),
    }
    assert all("command" not in tool["tool"] for tool in result["tool_trace"])


def test_sensor_investigation_states_its_limit(system):
    client, _, event, incident = create_incident(
        system, "robot-3", sensor="failed", battery=80
    )
    result = client.post(f"/api/incidents/{incident['id']}/investigate").json()
    assert result["confidence"] == "supported"
    assert event["event_id"] in {item["id"] for item in result["citations"]}
    assert "do not distinguish" in result["limitations"][0]


def test_disconnection_investigation_does_not_invent_triggering_event(system):
    client, clock, app = system
    mission = client.post(
        "/api/missions",
        json={"robot_id": "robot-4", "waypoints": [{"x": 1, "y": 1}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    from datetime import timedelta

    clock[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    incident = client.get("/api/incidents").json()[0]
    result = client.post(f"/api/incidents/{incident['id']}/investigate").json()
    assert result["confidence"] == "limited"
    assert "no telemetry event" in result["finding"]
    assert not any(item["type"] == "event" for item in result["citations"])
    assert any(item["id"] == "DOC-CONNECTION-001" for item in result["citations"])


def test_missing_referenced_event_is_insufficient():
    incident = {
        "id": "incident-missing",
        "robot_id": "robot-1",
        "mission_id": "mission-1",
        "type": "sensor_failure",
        "event_ids": ["missing-event"],
    }
    result = investigate(incident, {"id": "mission-1"}, [])
    assert result["confidence"] == "insufficient"
    assert "cannot verify" in result["finding"]
    assert not any(item["type"] == "event" for item in result["citations"])


def test_unknown_fault_returns_no_unsupported_diagnosis():
    incident = {
        "id": "unknown",
        "robot_id": "robot-1",
        "mission_id": None,
        "type": "unrecognized_fault",
        "event_ids": [],
    }
    result = investigate(incident, None, [])
    assert result["confidence"] == "insufficient"
    assert result["citations"] == []
    assert retrieve_guides("unrecognized_fault") == []


def test_missing_incident_returns_404(system):
    client, _, _ = system
    assert client.post("/api/incidents/missing/investigate").status_code == 404
