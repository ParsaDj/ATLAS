from datetime import timedelta


def login(client, username, password):
    client.cookies.clear()
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()["user"]


def create_user(client, username, role):
    response = client.post(
        "/api/users",
        json={
            "username": username,
            "password": f"{username}-secure-password",
            "role": role,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_mission_writes_require_authentication_and_csrf(system):
    client, _, _ = system
    client.cookies.clear()
    response = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 1, "y": 1}]},
    )
    assert response.status_code == 401

    login(client, "atlas-admin", "atlas-test-admin-password")
    del client.headers["X-CSRF-Token"]
    response = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 1, "y": 1}]},
    )
    assert response.status_code == 403


def test_administrator_can_create_users_without_exposing_password_hash(system):
    client, _, _ = system
    created = create_user(client, "operator-one", "operator")
    assert created == {
        "id": created["id"],
        "username": "operator-one",
        "role": "operator",
        "active": True,
    }
    users = client.get("/api/users").json()
    assert {user["username"] for user in users} == {"atlas-admin", "operator-one"}
    assert all("password" not in key for user in users for key in user)


def test_roles_limit_mission_writes_but_allow_investigation(system):
    client, _, _ = system
    create_user(client, "tech-one", "technician")
    mission = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 1, "y": 1}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    response = client.post(
        "/api/telemetry",
        json={
            "event_id": "auth-sensor-fault",
            "robot_id": "robot-1",
            "mission_id": mission["id"],
            "occurred_at": "2026-10-01T00:00:00Z",
            "position": {"x": 0, "y": 0},
            "battery": 80,
            "sensor_status": "failed",
        },
    )
    assert response.status_code == 200
    incident = client.get("/api/incidents").json()[0]

    login(client, "tech-one", "tech-one-secure-password")
    response = client.post(
        "/api/missions",
        json={"robot_id": "robot-2", "waypoints": [{"x": 1, "y": 1}]},
    )
    assert response.status_code == 403
    response = client.post(f"/api/incidents/{incident['id']}/investigate")
    assert response.status_code == 200
    assert response.json()["confidence"] == "supported"


def test_audit_log_records_actor_and_atomic_mission_actions(system):
    client, _, _ = system
    mission = client.post(
        "/api/missions",
        json={"robot_id": "robot-2", "waypoints": [{"x": 2, "y": 2}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    client.post(
        f"/api/missions/{mission['id']}/cancel",
        json={"reason": "Audit verification"},
    )

    records = client.get("/api/audit-logs").json()
    mission_records = [record for record in records if record["resource_id"] == mission["id"]]
    assert {record["action"] for record in mission_records} == {
        "mission.create",
        "mission.approve",
        "mission.cancel",
    }
    assert {record["actor_username"] for record in mission_records} == {"atlas-admin"}
    assert next(
        record for record in mission_records if record["action"] == "mission.cancel"
    )["details"] == {"reason": "Audit verification"}


def test_session_expires_after_eight_hours(system):
    client, clock, _ = system
    assert client.get("/api/auth/me").status_code == 200
    clock[0] += timedelta(hours=8, seconds=1)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Session expired or invalid"
