from datetime import datetime, timezone

import httpx
import pytest

from robotics.atlas_bridge import AtlasBridge, TelemetryEvent, TelemetryOutbox, ros_event_id


BRIDGE_KEY = "atlas-test-bridge-key-1234567890"


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
