from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.migrations import upgrade_database
from robotics.atlas_bridge import (
    AtlasBridge,
    MissionCoordinator,
    TelemetryEvent,
    TelemetryOutbox,
    ros_event_id,
)


BRIDGE_KEY = "atlas-test-bridge-key-1234567890"
PREVIOUS_BRIDGE_KEY = "atlas-previous-bridge-key-1234567890"


def observation(event_id="ros:robot-1:1"):
    return TelemetryEvent(
        event_id=event_id,
        robot_id="robot-1",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        x=1.25,
        y=-2.5,
        battery=82,
    )


def test_telemetry_requires_machine_credentials(system):
    client, _, _ = system
    body = observation().payload()
    del client.headers["X-ATLAS-Bridge-Key"]
    assert client.post("/api/telemetry", json=body).status_code == 401
    client.headers["X-ATLAS-Bridge-Key"] = "wrong-key"
    assert client.post("/api/telemetry", json=body).status_code == 401


def test_bridge_key_rotation_accepts_active_and_previous_keys(database_url):
    upgrade_database(database_url)
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password="atlas-test-admin-password",
        telemetry_api_key=BRIDGE_KEY,
        telemetry_previous_api_key=PREVIOUS_BRIDGE_KEY,
    )
    with TestClient(app) as client:
        body = observation("rotation-active").payload()
        active = client.post(
            "/api/telemetry",
            json=body,
            headers={"X-ATLAS-Bridge-Key": BRIDGE_KEY},
        )
        assert active.status_code == 200

        previous_body = observation("rotation-previous").payload()
        previous = client.post(
            "/api/telemetry",
            json=previous_body,
            headers={"X-ATLAS-Bridge-Key": PREVIOUS_BRIDGE_KEY},
        )
        assert previous.status_code == 200

        rejected = client.post(
            "/api/telemetry",
            json=observation("rotation-rejected").payload(),
            headers={"X-ATLAS-Bridge-Key": "unknown-bridge-key-1234567890"},
        )
        assert rejected.status_code == 401


def test_bridge_rotation_rejects_duplicate_keys(database_url):
    upgrade_database(database_url)
    with pytest.raises(ValueError, match="must differ"):
        create_app(
            database_url,
            monitor=False,
            bootstrap_admin_password="atlas-test-admin-password",
            telemetry_api_key=BRIDGE_KEY,
            telemetry_previous_api_key=BRIDGE_KEY,
        )


def test_per_robot_bridge_identity_limits_ingestion_and_reads(database_url):
    robot_1_key = "robot-1-scoped-bridge-key-1234567890"
    robot_2_key = "robot-2-scoped-bridge-key-1234567890"
    upgrade_database(database_url)
    app = create_app(
        database_url,
        monitor=False,
        bootstrap_admin_password="atlas-test-admin-password",
        robot_telemetry_api_keys={
            "robot-1": [robot_1_key],
            "robot-2": [robot_2_key],
        },
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "atlas-admin",
                "password": "atlas-test-admin-password",
            },
        ).json()
        client.headers["X-CSRF-Token"] = login["csrf_token"]
        robot_1_mission = client.post(
            "/api/missions",
            json={"robot_id": "robot-1", "waypoints": [{"x": 1, "y": 1}]},
        ).json()
        robot_2_mission = client.post(
            "/api/missions",
            json={"robot_id": "robot-2", "waypoints": [{"x": 2, "y": 2}]},
        ).json()
        client.cookies.clear()
        client.headers.pop("X-CSRF-Token")
        client.headers["X-ATLAS-Bridge-Key"] = robot_1_key

        assert client.post(
            "/api/telemetry", json=observation("robot-1-scoped-event").payload()
        ).status_code == 200
        wrong_robot = observation("robot-2-forbidden-event").payload()
        wrong_robot["robot_id"] = "robot-2"
        assert client.post("/api/telemetry", json=wrong_robot).status_code == 403

        missions = client.get("/api/missions").json()
        assert [mission["id"] for mission in missions] == [robot_1_mission["id"]]
        assert client.get(f"/api/missions/{robot_1_mission['id']}").status_code == 200
        assert client.get(f"/api/missions/{robot_2_mission['id']}").status_code == 403
        assert [robot["id"] for robot in client.get("/api/robots").json()] == [
            "robot-1"
        ]


def test_per_robot_bridge_keys_must_be_unique(database_url):
    upgrade_database(database_url)
    shared = "shared-robot-bridge-key-1234567890"
    with pytest.raises(ValueError, match="unique across robot identities"):
        create_app(
            database_url,
            monitor=False,
            bootstrap_admin_password="atlas-test-admin-password",
            robot_telemetry_api_keys={"robot-1": shared, "robot-2": shared},
        )

    with pytest.raises(ValueError, match="Facility and robot bridge keys"):
        create_app(
            database_url,
            monitor=False,
            bootstrap_admin_password="atlas-test-admin-password",
            telemetry_api_key=shared,
            robot_telemetry_api_keys={"robot-1": shared},
        )


def test_bridge_delivers_and_acknowledges_event(system, tmp_path):
    client, _, _ = system
    outbox = TelemetryOutbox(tmp_path / "outbox.db")
    result = AtlasBridge(client, "robot-1", BRIDGE_KEY, outbox).submit(observation())
    assert result.delivered == 1
    assert result.retained == 0
    assert client.get("/api/events/ros:robot-1:1").status_code == 200


def test_outbox_survives_transient_api_failure(system, tmp_path):
    def unavailable(_request):
        return httpx.Response(503, text="offline")

    path = tmp_path / "outbox.db"
    with httpx.Client(
        transport=httpx.MockTransport(unavailable), base_url="http://atlas"
    ) as unavailable_client:
        first = TelemetryOutbox(path)
        result = AtlasBridge(unavailable_client, "robot-1", BRIDGE_KEY, first).submit(
            observation()
        )
        assert result.retained == 1
        first.close()

    client, _, _ = system
    restarted = TelemetryOutbox(path)
    result = AtlasBridge(client, "robot-1", BRIDGE_KEY, restarted).flush()
    assert result.delivered == 1
    assert result.retained == 0


def test_invalid_event_is_quarantined_without_blocking_queue(system, tmp_path):
    client, _, _ = system
    outbox = TelemetryOutbox(tmp_path / "outbox.db")
    invalid = TelemetryEvent(
        event_id="unknown-robot-event",
        robot_id="unregistered-robot",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
        x=0,
        y=0,
        battery=100,
    )
    result = AtlasBridge(client, "unregistered-robot", BRIDGE_KEY, outbox).submit(invalid)
    assert result.quarantined == 1
    assert result.retained == 0
    assert outbox.rejected_count() == 1


def test_outbox_rejects_event_id_reuse(tmp_path):
    outbox = TelemetryOutbox(tmp_path / "outbox.db")
    outbox.enqueue(observation())
    changed = TelemetryEvent(**{**observation().__dict__, "battery": 81})
    with pytest.raises(ValueError, match="another payload"):
        outbox.enqueue(changed)


def test_bridge_fetches_only_its_active_mission(system, tmp_path):
    client, _, _ = system
    created = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 2, "y": 3}]},
    ).json()
    assert client.post(f"/api/missions/{created['id']}/approve").status_code == 200
    bridge = AtlasBridge(
        client, "robot-1", BRIDGE_KEY, TelemetryOutbox(tmp_path / "outbox.db")
    )
    assert bridge.active_mission()["id"] == created["id"]


def test_ros_event_id_is_stable_and_validated():
    first = ros_event_id("robot-1", 1_234_567_890, 7)
    assert first == ros_event_id("robot-1", 1_234_567_890, 7)
    assert first != ros_event_id("robot-1", 1_234_567_890, 8)
    assert len(first) <= 128
    with pytest.raises(ValueError):
        ros_event_id("robot-1", -1)


def test_mission_coordinator_starts_cancels_and_replaces_goal():
    coordinator = MissionCoordinator()
    first = {"id": "mission-1", "waypoints": [{"x": 1, "y": 2}]}
    second = {"id": "mission-2", "waypoints": [{"x": 3, "y": 4}]}
    assert coordinator.reconcile(first).action == "start"
    assert coordinator.reconcile(first) is None
    cancel = coordinator.reconcile(second)
    assert cancel.action == "cancel"
    assert cancel.mission == first
    assert coordinator.reconcile(second) is None
    replacement = coordinator.cancelled()
    assert replacement.action == "start"
    assert replacement.mission == second


def test_mission_coordinator_cancels_removed_goal():
    coordinator = MissionCoordinator()
    mission = {"id": "mission-1", "waypoints": []}
    coordinator.reconcile(mission)
    assert coordinator.reconcile(None).action == "cancel"
    assert coordinator.cancelled() is None
    assert coordinator.active is None


def test_finished_goal_waits_for_api_terminal_state_without_restarting():
    coordinator = MissionCoordinator()
    mission = {"id": "mission-1", "waypoints": []}
    coordinator.reconcile(mission)
    assert coordinator.finished(mission["id"]) is None
    assert coordinator.reconcile(mission) is None
    assert coordinator.reconcile(None) is None
    assert coordinator.active is None


def test_navigation_failure_fails_mission_and_creates_incident(system, tmp_path):
    client, clock, _ = system
    mission = client.post(
        "/api/missions",
        json={"robot_id": "robot-1", "waypoints": [{"x": 2, "y": 3}]},
    ).json()
    client.post(f"/api/missions/{mission['id']}/approve")
    event = TelemetryEvent(
        event_id="navigation-failure-1",
        robot_id="robot-1",
        mission_id=mission["id"],
        occurred_at=clock[0].isoformat(),
        x=0,
        y=0,
        battery=90,
        navigation_status="failed",
    )
    bridge = AtlasBridge(
        client, "robot-1", BRIDGE_KEY, TelemetryOutbox(tmp_path / "outbox.db")
    )
    assert bridge.submit(event).delivered == 1
    assert client.get(f"/api/missions/{mission['id']}").json()["status"] == "failed"
    incident = client.get("/api/incidents").json()[0]
    assert incident["type"] == "navigation_failure"
    assert incident["event_ids"] == [event.event_id]
