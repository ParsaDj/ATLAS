"""Deterministic generated traces for mission and telemetry invariants."""
import random
from datetime import timedelta

from simulator.fleet import sample


TRACE_COUNT = 50
STEPS_PER_TRACE = 12
SEED = 20261009
TERMINAL_STATES = {"completed", "failed", "cancelled"}


def test_generated_operation_traces_preserve_operational_invariants(system):
    client, clock, _ = system
    rng = random.Random(SEED)

    for trace in range(TRACE_COUNT):
        robot = f"robot-{trace % 5 + 1}"
        created = client.post(
            "/api/missions",
            json={"robot_id": robot, "waypoints": [{"x": 3, "y": trace % 7}]},
        )
        assert created.status_code == 201, f"trace={trace} create"
        mission_id = created.json()["id"]
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200

        accepted: dict[str, dict] = {}
        for step in range(STEPS_PER_TRACE):
            action = rng.choice(("healthy", "stale", "duplicate", "substitute"))
            if action in {"duplicate", "substitute"} and not accepted:
                action = "healthy"

            if action == "duplicate":
                event = rng.choice(list(accepted.values()))
                response = client.post("/api/telemetry", json=event)
                assert response.status_code == 200, f"trace={trace} duplicate"
                assert response.json()["duplicate"] is True
            elif action == "substitute":
                event = dict(rng.choice(list(accepted.values())))
                event["battery"] = event["battery"] - 1
                response = client.post("/api/telemetry", json=event)
                assert response.status_code == 409, f"trace={trace} substitution"
            else:
                clock[0] += timedelta(seconds=1)
                event = sample(
                    robot,
                    mission_id,
                    0,
                    f"state-machine:{trace}:{step}",
                    (
                        clock[0] - timedelta(minutes=5)
                        if action == "stale"
                        else clock[0]
                    ).isoformat(),
                )
                event["battery"] = 80
                event["sensor_status"] = "ok"
                event["mission_status"] = "running"
                response = client.post("/api/telemetry", json=event)
                assert response.status_code == 200, f"trace={trace} {action}"
                accepted[event["event_id"]] = event

            assert client.get(f"/api/missions/{mission_id}").json()["status"] == "running"

        terminal_action = rng.choice(("complete", "fault", "cancel"))
        terminal_event = None
        if terminal_action == "cancel":
            response = client.post(
                f"/api/missions/{mission_id}/cancel",
                json={"reason": f"Generated trace {trace}"},
            )
            assert response.status_code == 200
            expected_terminal = "cancelled"
        else:
            clock[0] += timedelta(seconds=1)
            terminal_event = sample(
                robot,
                mission_id,
                0,
                f"state-machine:{trace}:terminal",
                clock[0].isoformat(),
            )
            terminal_event["battery"] = 80
            terminal_event["sensor_status"] = (
                "failed" if terminal_action == "fault" else "ok"
            )
            terminal_event["mission_status"] = (
                "running" if terminal_action == "fault" else "completed"
            )
            response = client.post("/api/telemetry", json=terminal_event)
            assert response.status_code == 200
            accepted[terminal_event["event_id"]] = terminal_event
            expected_terminal = "failed" if terminal_action == "fault" else "completed"

        assert expected_terminal in TERMINAL_STATES
        assert client.get(f"/api/missions/{mission_id}").json()["status"] == expected_terminal

        # Later observations and repeated transitions must not resurrect or
        # rewrite a terminal mission.
        clock[0] += timedelta(seconds=1)
        late = sample(
            robot,
            mission_id,
            0,
            f"state-machine:{trace}:late",
            clock[0].isoformat(),
        )
        late["battery"] = 80
        late["sensor_status"] = "ok"
        late["mission_status"] = "running"
        assert client.post("/api/telemetry", json=late).status_code == 200
        accepted[late["event_id"]] = late
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 409
        assert client.post(
            f"/api/missions/{mission_id}/cancel",
            json={"reason": "Repeated terminal transition"},
        ).status_code == 409
        assert client.get(f"/api/missions/{mission_id}").json()["status"] == expected_terminal

        if terminal_event:
            replay = client.post("/api/telemetry", json=terminal_event)
            assert replay.status_code == 200
            assert replay.json()["duplicate"] is True

        stored = client.get("/api/events", params={"mission_id": mission_id, "limit": 1000}).json()
        assert {event["event_id"] for event in stored} == set(accepted)
        assert len(stored) == len(accepted)

        incidents = client.get("/api/incidents", params={"mission_id": mission_id}).json()
        assert [incident["type"] for incident in incidents] == (
            ["sensor_failure"] if terminal_action == "fault" else []
        )

        audit = client.get("/api/audit-logs", params={"limit": 1000}).json()
        actions = {
            entry["action"] for entry in audit if entry["resource_id"] == mission_id
        }
        expected_actions = {"mission.create", "mission.approve"}
        if terminal_action == "cancel":
            expected_actions.add("mission.cancel")
        assert actions == expected_actions
