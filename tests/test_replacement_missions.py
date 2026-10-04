from simulator.fleet import sample


def failed_incident(system):
    client, clock, _ = system
    source = client.post(
        "/api/missions",
        json={"robot_id": "robot-3", "waypoints": [{"x": 1, "y": 2}]},
    ).json()
    client.post(f"/api/missions/{source['id']}/approve")
    event = sample(
        "robot-3", source["id"], 0, "replacement", clock[0].isoformat()
    )
    event["sensor_status"] = "failed"
    client.post("/api/telemetry", json=event)
    incident = next(
        row
        for row in client.get("/api/incidents").json()
        if row["mission_id"] == source["id"]
    )
    return client, source, incident


def propose(client, incident_id, waypoints=None):
    return client.post(
        f"/api/incidents/{incident_id}/replacement-missions",
        json={"waypoints": waypoints or [{"x": 4, "y": 5}, {"x": 6, "y": 7}]},
    )


def login_as_technician(client):
    client.post(
        "/api/users",
        json={
            "username": "replacement-tech",
            "password": "replacement-tech-password",
            "role": "technician",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={
            "username": "replacement-tech",
            "password": "replacement-tech-password",
        },
    )
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def test_replacement_proposal_links_source_and_uses_edited_route(system):
    client, source, incident = failed_incident(system)
    response = propose(client, incident["id"])
    assert response.status_code == 201
    replacement = response.json()
    assert replacement["status"] == "pending"
    assert replacement["robot_id"] == source["robot_id"]
    assert replacement["replacement_for_mission_id"] == source["id"]
    assert replacement["source_incident_id"] == incident["id"]
    assert replacement["waypoints"] == [{"x": 4.0, "y": 5.0}, {"x": 6.0, "y": 7.0}]
    listed = client.get(
        "/api/missions", params={"source_incident_id": incident["id"]}
    ).json()
    assert [mission["id"] for mission in listed] == [replacement["id"]]


def test_replacement_requires_failed_source_and_operator_role(system):
    client, clock, _ = system
    unassigned = sample("robot-2", None, 3, "unassigned", clock[0].isoformat())
    client.post("/api/telemetry", json=unassigned)
    incident_without_mission = client.get("/api/incidents").json()[0]
    assert propose(client, incident_without_mission["id"]).status_code == 409

    # Use a fresh incident after the unassigned fault to verify role enforcement.
    _, _, incident = failed_incident(system)
    login_as_technician(client)
    assert propose(client, incident["id"]).status_code == 403


def test_incident_allows_only_one_active_replacement(system):
    client, _, incident = failed_incident(system)
    assert propose(client, incident["id"]).status_code == 201
    assert propose(client, incident["id"]).status_code == 409


def test_replacement_requires_separate_approval_and_is_audited(system):
    client, _, incident = failed_incident(system)
    replacement = propose(client, incident["id"]).json()
    assert replacement["status"] == "pending"
    approved = client.post(f"/api/missions/{replacement['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "running"
    logs = client.get("/api/audit-logs").json()
    actions = [
        row["action"] for row in logs if row["resource_id"] == replacement["id"]
    ]
    assert set(actions) == {
        "mission.replacement_approve",
        "mission.replacement_propose",
    }
