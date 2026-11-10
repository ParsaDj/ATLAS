from apps.ai_agent.service import investigate, retrieve_guides
from simulator.fleet import sample


def create_incident(system, robot, *, sensor="ok", navigation="ok", battery=80):
    client, clock, _ = system
    created = client.post(
        "/api/missions",
        json={"robot_id": robot, "waypoints": [{"x": 1, "y": 1}]},
    ).json()
    client.post(f"/api/missions/{created['id']}/approve")
    body = sample(robot, created["id"], 0, "investigation", clock[0].isoformat())
    body["sensor_status"] = sensor
    body["navigation_status"] = navigation
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
    assert {(item["type"], item["id"]) for item in result["citations"]} == {
        ("event", event["event_id"]),
        ("mission", mission["id"]),
        ("document", "DOC-BATTERY-001"),
    }
    document = next(item for item in result["citations"] if item["type"] == "document")
    assert document["version"] == "1.0"
    assert len(document["sha256"]) == 64
    assert all("command" not in tool["tool"] for tool in result["tool_trace"])


def test_sensor_investigation_states_its_limit(system):
    client, _, event, incident = create_incident(
        system, "robot-3", sensor="failed", battery=80
    )
    result = client.post(f"/api/incidents/{incident['id']}/investigate").json()
    assert result["confidence"] == "supported"
    assert event["event_id"] in {item["id"] for item in result["citations"]}
    assert "do not distinguish" in result["limitations"][0]


def test_navigation_failure_investigation_cites_nav2_guide(system):
    client, _, event, incident = create_incident(
        system, "robot-1", navigation="failed"
    )
    result = client.post(f"/api/incidents/{incident['id']}/investigate").json()
    assert result["confidence"] == "supported"
    assert "navigation mission failure" in result["finding"]
    assert event["event_id"] in {item["id"] for item in result["citations"]}
    assert "DOC-NAVIGATION-001" in {item["id"] for item in result["citations"]}


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


def test_seeded_document_revisions_are_queryable_and_content_addressed(system):
    client, _, _ = system
    response = client.get("/api/documents?fault=low_battery")
    assert response.status_code == 200
    documents = response.json()
    assert len(documents) == 1
    document = documents[0]
    assert document["id"] == "DOC-BATTERY-001"
    assert document["version"] == "1.0"
    assert document["approved"] is True
    assert len(document["sha256"]) == 64
    assert client.get(
        "/api/documents/DOC-BATTERY-001/versions/1.0"
    ).json() == document


def test_new_approved_revision_is_used_without_mutating_prior_revision(system):
    client, _, _ = system
    body = {
        "id": "DOC-BATTERY-001",
        "version": "2.0",
        "fault": "low_battery",
        "title": "Low battery response version two",
        "content": "Verified version two instructions for a synthetic low battery alert.",
        "next_step": "Use the version two battery verification procedure.",
    }
    created = client.post("/api/documents", json=body)
    assert created.status_code == 201
    assert created.json()["approved"] is False
    assert client.post("/api/documents", json=body).status_code == 409
    visible = client.get("/api/documents?fault=low_battery").json()
    assert [document["version"] for document in visible] == ["1.0"]

    approved = client.post(
        "/api/documents/DOC-BATTERY-001/versions/2.0/approve"
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert client.post(
        "/api/documents/DOC-BATTERY-001/versions/2.0/approve"
    ).status_code == 409

    _, _, _, incident = create_incident(system, "robot-5", battery=10)
    result = client.post(f"/api/incidents/{incident['id']}/investigate").json()
    citation = next(item for item in result["citations"] if item["type"] == "document")
    assert citation["id"] == "DOC-BATTERY-001"
    assert citation["version"] == "2.0"
    assert result["recommended_next_step"] == body["next_step"]
    assert client.get(
        "/api/documents/DOC-BATTERY-001/versions/1.0"
    ).status_code == 200

    logs = client.get("/api/audit-logs").json()
    assert any(
        row["action"] == "document.create_revision"
        and row["details"]["version"] == "2.0"
        for row in logs
    )
    assert any(
        row["action"] == "document.approve_revision"
        and row["details"]["version"] == "2.0"
        for row in logs
    )


def test_retired_revision_is_preserved_but_excluded_from_new_investigations(system):
    client, _, _ = system
    body = {
        "id": "DOC-BATTERY-001",
        "version": "2.0",
        "fault": "low_battery",
        "title": "Low battery response version two",
        "content": "A revision that will be retired after an operational review.",
        "next_step": "Use the temporary version two verification procedure.",
    }
    assert client.post("/api/documents", json=body).status_code == 201
    assert client.post(
        "/api/documents/DOC-BATTERY-001/versions/2.0/approve"
    ).status_code == 200

    _, _, _, first_incident = create_incident(system, "robot-1", battery=10)
    first = client.post(
        f"/api/incidents/{first_incident['id']}/investigate"
    ).json()
    first_document = next(
        item for item in first["citations"] if item["type"] == "document"
    )
    assert first_document["version"] == "2.0"

    retired = client.post(
        "/api/documents/DOC-BATTERY-001/versions/2.0/retire",
        json={"reason": "Superseded after the verification procedure changed."},
    )
    assert retired.status_code == 200
    assert retired.json()["retired_at"] is not None
    assert retired.json()["retired_by"] is not None
    assert client.post(
        "/api/documents/DOC-BATTERY-001/versions/2.0/retire",
        json={"reason": "Duplicate retirement attempt."},
    ).status_code == 409

    active = client.get("/api/documents?fault=low_battery").json()
    assert [document["version"] for document in active] == ["1.0"]
    retired_revisions = client.get(
        "/api/documents?fault=low_battery&approved=true&retired=true"
    ).json()
    assert [document["version"] for document in retired_revisions] == ["2.0"]

    _, _, _, second_incident = create_incident(system, "robot-2", battery=9)
    second = client.post(
        f"/api/incidents/{second_incident['id']}/investigate"
    ).json()
    second_document = next(
        item for item in second["citations"] if item["type"] == "document"
    )
    assert second_document["version"] == "1.0"

    logs = client.get("/api/audit-logs").json()
    retirement = next(
        row for row in logs if row["action"] == "document.retire_revision"
    )
    assert retirement["details"] == {
        "version": "2.0",
        "sha256": retired.json()["sha256"],
        "reason": "Superseded after the verification procedure changed.",
    }


def test_draft_document_cannot_be_retired(system):
    client, _, _ = system
    body = {
        "id": "DOC-SENSOR-DRAFT",
        "version": "1.0",
        "fault": "sensor_failure",
        "title": "Unreviewed sensor procedure",
        "content": "This draft has not passed the required operational review.",
        "next_step": "Do not use this draft in an investigation.",
    }
    assert client.post("/api/documents", json=body).status_code == 201
    response = client.post(
        "/api/documents/DOC-SENSOR-DRAFT/versions/1.0/retire",
        json={"reason": "Drafts should not enter retirement workflow."},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Only approved revisions can be retired"


def test_only_administrators_can_view_or_retire_retired_guidance(system):
    client, _, _ = system
    created = client.post(
        "/api/users",
        json={
            "username": "knowledge-operator",
            "password": "knowledge-operator-password",
            "role": "operator",
        },
    )
    assert created.status_code == 201
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "username": "knowledge-operator",
            "password": "knowledge-operator-password",
        },
    )
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]

    assert client.get("/api/documents?retired=true").status_code == 403
    assert client.post(
        "/api/documents/DOC-BATTERY-001/versions/1.0/retire",
        json={"reason": "Operators must not change approved guidance."},
    ).status_code == 403
