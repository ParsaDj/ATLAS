from simulator.fleet import sample


def create_user(client, username, role="technician"):
    response = client.post(
        "/api/users",
        json={
            "username": username,
            "password": "maintenance-password-123",
            "role": role,
        },
    )
    assert response.status_code == 201
    return response.json()


def login(client, username, password="maintenance-password-123"):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def create_incident(system, robot="robot-1"):
    client, clock, _ = system
    mission = client.post(
        "/api/missions",
        json={"robot_id": robot, "waypoints": [{"x": 1, "y": 1}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    event = sample(robot, mission["id"], 0, "ticket", clock[0].isoformat())
    event["navigation_status"] = "failed"
    assert client.post("/api/telemetry", json=event).status_code == 200
    return client.get("/api/incidents").json()[0]


def draft_ticket(client, incident_id, technician="field-tech"):
    response = client.post(
        f"/api/incidents/{incident_id}/tickets",
        json={
            "summary": "Inspect navigation sensors and costmap observations",
            "assigned_technician": technician,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ticket_requires_active_technician_and_is_unique(system):
    client, _, _ = system
    incident = create_incident(system)
    assert (
        client.post(
            f"/api/incidents/{incident['id']}/tickets",
            json={"summary": "Inspect robot", "assigned_technician": "missing"},
        ).status_code
        == 422
    )
    create_user(client, "field-tech")
    ticket = draft_ticket(client, incident["id"])
    assert ticket["status"] == "draft"
    assert ticket["assigned_technician"] == "field-tech"
    assert (
        client.post(
            f"/api/incidents/{incident['id']}/tickets",
            json={"summary": "Duplicate work", "assigned_technician": "field-tech"},
        ).status_code
        == 409
    )


def test_ticket_requires_approval_before_assigned_technician_can_work(system):
    client, _, _ = system
    create_user(client, "field-tech")
    incident = create_incident(system)
    ticket = draft_ticket(client, incident["id"])
    login(client, "field-tech")
    assert client.post(f"/api/tickets/{ticket['id']}/start").status_code == 409
    assert client.post(f"/api/tickets/{ticket['id']}/approve").status_code == 403


def test_approved_ticket_resolves_linked_incident_and_is_audited(system):
    client, _, _ = system
    technician = create_user(client, "field-tech")
    incident = create_incident(system)
    ticket = draft_ticket(client, incident["id"])
    approved = client.post(f"/api/tickets/{ticket['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    login(client, "field-tech")
    started = client.post(f"/api/tickets/{ticket['id']}/start")
    assert started.status_code == 200
    resolved = client.post(
        f"/api/tickets/{ticket['id']}/resolve",
        json={"resolution": "Cleared stale costmap and verified localization."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert (
        client.get(f"/api/incidents/{incident['id']}").json()["status"]
        == "resolved"
    )

    login(client, "atlas-admin", "atlas-test-admin-password")
    logs = client.get("/api/audit-logs").json()
    resolved_log = next(log for log in logs if log["action"] == "ticket.resolve")
    assert resolved_log["actor_id"] == technician["id"]
    assert resolved_log["resource_id"] == ticket["id"]


def test_unassigned_technician_cannot_start_ticket(system):
    client, _, _ = system
    create_user(client, "field-tech")
    create_user(client, "other-tech")
    incident = create_incident(system)
    ticket = draft_ticket(client, incident["id"])
    client.post(f"/api/tickets/{ticket['id']}/approve")
    login(client, "other-tech")
    assert client.post(f"/api/tickets/{ticket['id']}/start").status_code == 403


def test_ticket_lists_require_authentication_and_support_filters(system):
    client, _, _ = system
    create_user(client, "field-tech")
    incident = create_incident(system)
    ticket = draft_ticket(client, incident["id"])
    response = client.get(
        "/api/tickets", params={"incident_id": incident["id"], "status": "draft"}
    )
    assert [row["id"] for row in response.json()] == [ticket["id"]]
    client.cookies.clear()
    assert client.get("/api/tickets").status_code == 401
