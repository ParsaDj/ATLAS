from simulator.fleet import sample


def report_fixture(system):
    client, clock, _ = system
    client.post(
        "/api/users",
        json={
            "username": "report-tech",
            "password": "report-technician-password",
            "role": "technician",
        },
    )
    mission = client.post(
        "/api/missions",
        json={"robot_id": "robot-3", "waypoints": [{"x": 1, "y": 2}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    event = sample(
        "robot-3", mission["id"], 0, "report", clock[0].isoformat()
    )
    event["sensor_status"] = "failed"
    client.post("/api/telemetry", json=event)
    incident = client.get("/api/incidents").json()[0]
    ticket = client.post(
        f"/api/incidents/{incident['id']}/tickets",
        json={
            "summary": "Inspect <script>alert('unsafe')</script> sensor",
            "assigned_technician": "report-tech",
        },
    ).json()
    return client, mission, event, incident, ticket


def test_incident_report_separates_facts_findings_and_escapes_content(system):
    client, mission, event, incident, ticket = report_fixture(system)
    response = client.get(f"/api/incidents/{incident['id']}/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="atlas-incident-{incident["id"]}.html"'
    )
    report = response.text
    assert "Recorded incident facts" in report
    assert "Evidence-based investigation" in report
    assert "Maintenance history" in report
    assert mission["id"] in report
    assert event["event_id"] in report
    assert ticket["id"] in report
    assert "DOC-SENSOR-001" in report
    assert "<script>" not in report
    assert "&lt;script&gt;" in report


def test_mission_report_includes_route_telemetry_incidents_and_tickets(system):
    client, mission, event, incident, ticket = report_fixture(system)
    response = client.get(f"/api/missions/{mission['id']}/report.html")
    assert response.status_code == 200
    report = response.text
    assert "Mission facts" in report
    assert "Inspection route" in report
    assert "Telemetry summary" in report
    assert "Recorded events</th><td>1" in report
    assert incident["id"] in report
    assert ticket["id"] in report
    assert event["battery"] == 100


def test_report_generation_is_authenticated_and_audited(system):
    client, mission, _, incident, _ = report_fixture(system)
    client.get(f"/api/incidents/{incident['id']}/report.html")
    client.get(f"/api/missions/{mission['id']}/report.html")
    logs = client.get("/api/audit-logs").json()
    report_logs = [row for row in logs if row["action"] == "report.generate"]
    assert {(row["resource_type"], row["resource_id"]) for row in report_logs} == {
        ("incident", incident["id"]),
        ("mission", mission["id"]),
    }
    client.cookies.clear()
    assert client.get(f"/api/incidents/{incident['id']}/report.html").status_code == 401


def test_missing_report_resources_return_404(system):
    client, _, _ = system
    assert client.get("/api/incidents/missing/report.html").status_code == 404
    assert client.get("/api/missions/missing/report.html").status_code == 404
