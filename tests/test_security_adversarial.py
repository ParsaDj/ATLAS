from tests.test_auth import create_user, login
from simulator.fleet import sample


def without_identity(client):
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    client.headers.pop("X-ATLAS-Bridge-Key", None)


def test_operational_reads_require_session_or_valid_bridge(system):
    client, _, _ = system
    without_identity(client)
    paths = (
        "/api/robots",
        "/api/missions",
        "/api/events",
        "/api/incidents",
    )
    assert all(client.get(path).status_code == 401 for path in paths)

    client.headers["X-ATLAS-Bridge-Key"] = "forged-bridge-key-1234567890"
    assert all(client.get(path).status_code == 401 for path in paths)

    client.headers["X-ATLAS-Bridge-Key"] = "atlas-test-bridge-key-1234567890"
    assert all(client.get(path).status_code == 200 for path in paths)


def test_forged_bridge_cannot_ingest_telemetry(system):
    client, clock, _ = system
    without_identity(client)
    body = sample("robot-1", None, 0, "forged", clock[0].isoformat())
    client.headers["X-ATLAS-Bridge-Key"] = "forged-bridge-key-1234567890"

    assert client.post("/api/telemetry", json=body).status_code == 401

    client.headers["X-ATLAS-Bridge-Key"] = "atlas-test-bridge-key-1234567890"
    assert client.get("/api/events").json() == []


def test_event_id_substitution_is_rejected_without_state_change(system):
    client, clock, _ = system
    original = sample("robot-1", None, 0, "bridge-source", clock[0].isoformat())
    assert client.post("/api/telemetry", json=original).status_code == 200
    changed = {**original, "battery": 1}

    assert client.post("/api/telemetry", json=changed).status_code == 409
    stored = client.get(f"/api/events/{original['event_id']}").json()
    assert stored["battery"] == original["battery"]
    assert client.get("/api/incidents").json() == []


def test_non_admin_cannot_access_administration(system):
    client, _, _ = system
    create_user(client, "limited-operator", "operator")
    login(client, "limited-operator", "limited-operator-secure-password")

    assert client.get("/api/users").status_code == 403
    assert client.get("/api/audit-logs").status_code == 403
    assert client.post(
        "/api/users",
        json={
            "username": "escalated-user",
            "password": "escalated-user-secure-password",
            "role": "administrator",
        },
    ).status_code == 403


def test_csrf_token_cannot_be_replayed_with_another_session(system):
    client, _, _ = system
    create_user(client, "second-operator", "operator")
    first_csrf = client.headers["X-CSRF-Token"]
    login(client, "second-operator", "second-operator-secure-password")
    client.headers["X-CSRF-Token"] = first_csrf

    response = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 1, "y": 1}]},
    )
    assert response.status_code == 403
    assert client.get("/api/missions").json() == []


def test_logout_revokes_server_session(system):
    client, _, _ = system
    session_cookie = client.cookies.get("atlas_session")
    assert session_cookie
    assert client.post("/api/auth/logout").status_code == 204

    client.cookies.set("atlas_session", session_cookie)
    client.headers.pop("X-ATLAS-Bridge-Key", None)
    assert client.get("/api/robots").status_code == 401
