from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.migrations import upgrade_database
from conftest import TEST_ADMIN_PASSWORD, TEST_BRIDGE_KEY


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


def test_login_rate_limit_recovers_after_window(database_url):
    upgrade_database(database_url)
    limiter_time = [1000.0]
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password=TEST_ADMIN_PASSWORD,
        telemetry_api_key=TEST_BRIDGE_KEY,
        security_clock=lambda: limiter_time[0],
    )
    with TestClient(app) as client:
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"username": "atlas-admin", "password": "incorrect-password"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            json={"username": "atlas-admin", "password": TEST_ADMIN_PASSWORD},
        )
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "300"

        limiter_time[0] += 301
        recovered = client.post(
            "/api/auth/login",
            json={"username": "atlas-admin", "password": TEST_ADMIN_PASSWORD},
        )
        assert recovered.status_code == 200


def test_security_headers_cover_api_errors_and_https(database_url):
    upgrade_database(database_url)
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password=TEST_ADMIN_PASSWORD,
        telemetry_api_key=TEST_BRIDGE_KEY,
    )
    with TestClient(app, base_url="https://atlas.example") as client:
        response = client.get("/api/robots/missing")

    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")
