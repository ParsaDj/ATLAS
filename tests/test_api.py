from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from simulator.fleet import sample


def mission(client, robot="robot-2"):
    response = client.post("/api/missions", json={"robot_id": robot, "waypoints": [{"x": 1, "y": 2}]})
    assert response.status_code == 201
    mid = response.json()["id"]
    assert client.post(f"/api/missions/{mid}/approve").status_code == 200
    return mid


def event(time, mid, robot="robot-2", tick=3):
    return sample(robot, mid, tick, "test", time[0].isoformat())


def test_fleet_and_failure_duplicate(system):
    client, time, _ = system
    assert len(client.get("/api/robots").json()) == 5
    mid = mission(client)
    body = event(time, mid)
    assert client.post("/api/telemetry", json=body).json()["duplicate"] is False
    assert client.post("/api/telemetry", json=body).json()["duplicate"] is True
    incidents = client.get("/api/incidents").json()
    assert len(incidents) == 1
    assert incidents[0]["event_ids"] == [body["event_id"]]
    assert client.get(f"/api/incidents/{incidents[0]['id']}").json() == incidents[0]
    assert client.get(f"/api/missions/{mid}").json()["status"] == "failed"
    assert len(client.get("/api/robots/robot-2/telemetry").json()) == 1
    body["battery"] = 11
    assert client.post("/api/telemetry", json=body).status_code == 409


@pytest.mark.parametrize("robot,kind", [("robot-2", "low_battery"), ("robot-3", "sensor_failure")])
def test_repeated_fault_is_one_incident(system, robot, kind):
    client, time, _ = system
    mid = mission(client, robot)
    for tick in range(3, 6):
        time[0] += timedelta(seconds=5)
        assert client.post("/api/telemetry", json=event(time, mid, robot, tick)).status_code == 200
    incidents = client.get("/api/incidents").json()
    assert len(incidents) == 1
    assert incidents[0]["type"] == kind


def test_disconnect_and_recovery(system):
    client, time, app = system
    mid = mission(client, "robot-4")
    body = event(time, mid, "robot-4", 0)
    client.post("/api/telemetry", json=body)
    time[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    app.state.check_disconnects()
    assert client.get("/api/robots/robot-4").json()["status"] == "disconnected"
    assert len(client.get("/api/incidents").json()) == 1
    assert client.get(f"/api/missions/{mid}").json()["status"] == "failed"
    client.post("/api/telemetry", json=event(time, mid, "robot-4", 1))
    assert client.get("/api/robots/robot-4").json()["status"] == "online"
    assert client.get(f"/api/missions/{mid}").json()["status"] == "failed"


def test_states_and_completion(system):
    client, time, _ = system
    mid = mission(client, "robot-1")
    assert client.post(f"/api/missions/{mid}/approve").status_code == 409
    other = client.post("/api/missions", json={"robot_id": "robot-1", "waypoints": [{"x": 0, "y": 0}]}).json()["id"]
    assert client.post(f"/api/missions/{other}/approve").status_code == 409
    assert client.post("/api/telemetry", json=event(time, mid, "robot-1", 7)).status_code == 200
    assert client.get(f"/api/missions/{mid}").json()["status"] == "completed"
    assert client.post(f"/api/missions/{other}/approve").status_code == 200


def test_stale_event_does_not_regress_state(system):
    client, time, _ = system
    mid = mission(client)
    old = event(time, mid)
    time[0] += timedelta(seconds=10)
    client.post("/api/telemetry", json=event(time, mid, tick=0))
    client.post("/api/telemetry", json=old)
    assert client.get("/api/robots/robot-2").json()["battery"] == 100
    assert client.get("/api/incidents").json() == []
    assert len(client.get("/api/robots/robot-2/telemetry").json()) == 2


@pytest.mark.parametrize("field,value", [("battery", -1), ("battery", 101), ("sensor_status", "bad"), ("occurred_at", "2026-01-01T00:00:00"), ("unexpected", 1)])
def test_invalid_sample(system, field, value):
    client, time, _ = system
    body = event(time, None)
    body[field] = value
    assert client.post("/api/telemetry", json=body).status_code == 422


def test_reject_wrong_robot_and_future_time(system):
    client, time, _ = system
    mid = mission(client)
    assert client.post("/api/telemetry", json=event(time, mid, "robot-3")).status_code == 422
    body = event(time, mid)
    body["occurred_at"] = (time[0] + timedelta(minutes=2)).isoformat()
    assert client.post("/api/telemetry", json=body).status_code == 422
    assert client.get("/api/robots/missing").status_code == 404


def test_concurrent_duplicate_delivery(system):
    client, time, _ = system
    mid = mission(client)
    body = event(time, mid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post("/api/telemetry", json=body), range(8)))
    assert all(r.status_code == 200 for r in results)
    assert sum(not r.json()["duplicate"] for r in results) == 1
    assert len(client.get("/api/incidents").json()) == 1


def test_no_first_heartbeat(system):
    client, time, app = system
    mid = mission(client, "robot-4")
    time[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    assert client.get(f"/api/missions/{mid}").json()["status"] == "failed"


def test_complete_fleet_scenario(system):
    client, time, app = system
    missions = {f"robot-{n}": mission(client, f"robot-{n}") for n in range(1, 6)}
    for tick in range(10):
        for robot, mid in missions.items():
            if robot == "robot-4" and tick >= 3:
                continue
            assert client.post("/api/telemetry", json=event(time, mid, robot, tick)).status_code == 200
        time[0] += timedelta(seconds=5)
        app.state.check_disconnects()
    states = {robot: client.get(f"/api/missions/{mid}").json()["status"] for robot, mid in missions.items()}
    assert states == {"robot-1": "completed", "robot-2": "failed", "robot-3": "failed", "robot-4": "failed", "robot-5": "completed"}
    assert {i["type"] for i in client.get("/api/incidents").json()} == {"low_battery", "sensor_failure", "disconnection"}


def test_concurrent_approval_only_one_running(system):
    client, _, _ = system
    mids = [client.post("/api/missions", json={"robot_id": "robot-1", "waypoints": [{"x": 0, "y": 0}]}).json()["id"] for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda mid: client.post(f"/api/missions/{mid}/approve"), mids))
    assert sorted(r.status_code for r in results) == [200, 409]


def test_late_previous_mission_cannot_fail_new_mission(system):
    client, time, _ = system
    previous = mission(client, "robot-1")
    client.post("/api/telemetry", json=event(time, previous, "robot-1", 7))
    current = mission(client, "robot-1")
    time[0] += timedelta(seconds=5)
    delayed = event(time, previous, "robot-1", 8)
    delayed["sensor_status"] = "failed"
    assert client.post("/api/telemetry", json=delayed).status_code == 200
    assert client.get("/api/robots/robot-1").json()["status"] == "online"
    assert client.get(f"/api/missions/{current}").json()["status"] == "running"
    assert client.get("/api/incidents").json() == []


def test_disconnected_robot_new_mission_still_times_out(system):
    client, time, app = system
    first = mission(client, 'robot-4')
    time[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    assert client.get(f'/api/missions/{first}').json()['status'] == 'failed'
    second = mission(client, 'robot-4')
    time[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    assert client.get(f'/api/missions/{second}').json()['status'] == 'failed'
    assert len(client.get('/api/incidents').json()) == 2


def test_simultaneous_faults_are_both_recorded(system):
    client, time, _ = system
    mid = mission(client)
    body = event(time, mid)
    body['sensor_status'] = 'failed'
    assert client.post('/api/telemetry', json=body).status_code == 200
    assert {i['type'] for i in client.get('/api/incidents').json()} == {'low_battery', 'sensor_failure'}


def test_old_first_sample_does_not_claim_robot_online(system):
    client, time, _ = system
    body = event(time, None, 'robot-1', 0)
    body['occurred_at'] = (time[0] - timedelta(hours=1)).isoformat()
    assert client.post('/api/telemetry', json=body).status_code == 200
    assert client.get('/api/robots/robot-1').json()['status'] == 'unknown'


def test_cancel_and_resume_interrupted_fleet(system):
    client, time, _ = system
    mid = mission(client, 'robot-1')
    response = client.post(f'/api/missions/{mid}/cancel', json={'reason': 'Restart demo'})
    assert response.status_code == 200
    assert response.json()['cancellation_reason'] == 'Restart demo'
    assert response.json()['status'] == 'cancelled'
    assert client.post(f'/api/missions/{mid}/cancel', json={'reason': 'Again'}).status_code == 409
    time[0] += timedelta(seconds=5)
    client.post('/api/telemetry', json=event(time, mid, 'robot-1', 7))
    assert client.get(f'/api/missions/{mid}').json()['status'] == 'cancelled'
    assert mission(client, 'robot-1') != mid


def test_cancel_validation_and_terminal_state(system):
    client, time, _ = system
    mid = mission(client, 'robot-1')
    assert client.post(f'/api/missions/{mid}/cancel', json={'reason': '  '}).status_code == 422
    client.post('/api/telemetry', json=event(time, mid, 'robot-1', 7))
    assert client.post(f'/api/missions/{mid}/cancel', json={'reason': 'No'}).status_code == 409
    assert client.post('/api/missions/missing/cancel', json={'reason': 'No'}).status_code == 404


def test_filtered_paginated_history_and_event_evidence(system):
    client, time, _ = system
    mid = mission(client)
    for tick in range(3, 6):
        time[0] += timedelta(seconds=1)
        client.post('/api/telemetry', json=event(time, mid, tick=tick))
    other = mission(client, 'robot-1')
    assert len(client.get('/api/missions', params={'status': 'running'}).json()) == 1
    assert client.get('/api/missions', params={'robot_id': 'robot-1'}).json()[0]['id'] == other
    first = client.get('/api/events', params={'mission_id': mid, 'limit': 2}).json()
    second = client.get('/api/events', params={'mission_id': mid, 'limit': 2, 'offset': 2}).json()
    assert [r['event_id'] for r in first + second] == ['test:robot-2:5', 'test:robot-2:4', 'test:robot-2:3']
    assert client.get('/api/events', params={'robot_id': 'robot-1'}).json() == []
    incident = client.get('/api/incidents', params={'mission_id': mid}).json()[0]
    evidence = client.get(f"/api/events/{incident['event_ids'][0]}").json()
    assert evidence['battery'] == 12
    assert evidence['mission_id'] == mid
    assert client.get('/api/events/missing').status_code == 404


@pytest.mark.parametrize('path', ['/api/events', '/api/missions', '/api/incidents', '/api/robots/robot-1/telemetry'])
def test_pagination_rejects_unbounded_requests(system, path):
    client, _, _ = system
    assert client.get(path, params={'limit': 1001}).status_code == 422
    assert client.get(path, params={'offset': -1}).status_code == 422


def test_cancelled_unapproved_mission_rejects_telemetry(system):
    client, time, _ = system
    created = client.post('/api/missions', json={'robot_id': 'robot-1', 'waypoints': [{'x': 0, 'y': 0}]}).json()
    client.post(f"/api/missions/{created['id']}/cancel", json={'reason': 'Not approved'})
    response = client.post('/api/telemetry', json=event(time, created['id'], 'robot-1', 0))
    assert response.status_code == 422
    assert client.get('/api/robots/robot-1/telemetry').json() == []
