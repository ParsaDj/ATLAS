from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from simulator.worker import tick, next_sample


def create(client, points=None):
    response = client.post('/api/missions', json={'robot_id': 'robot-1', 'waypoints': points or [{'x': 2, 'y': 0}, {'x': 2, 'y': 2}]})
    assert response.status_code == 201
    mission = response.json()
    assert client.post(f"/api/missions/{mission['id']}/approve").status_code == 200
    return mission['id']


def advance(system):
    client, clock, _ = system
    clock[0] += timedelta(seconds=2)
    tick(client, clock=lambda: clock[0])


def state(client, mid):
    return client.get(f'/api/missions/{mid}').json()


def test_worker_executes_all_waypoints_and_idles_after_completion(system):
    client, _, _ = system
    mid = create(client)
    for count in range(1, 5):
        advance(system)
        current = state(client, mid)
        assert current['execution_step'] == count
        assert current['completed_waypoints'] == count // 2
    assert state(client, mid)['status'] == 'completed'
    advance(system)
    assert state(client, mid)['execution_step'] == 4
    assert client.get('/api/robots/robot-1').json()['status'] == 'online'
    assert client.get('/api/robots/robot-1').json()['position'] == {'x': 2, 'y': 2}


def test_restart_resumes_checkpoint_without_repeating_waypoint(system):
    client, _, _ = system
    mid = create(client)
    advance(system)
    advance(system)
    # Each tick has no process-local state, as in a fresh worker process.
    advance(system)
    assert state(client, mid)['execution_position'] == {'x': 2, 'y': 1}
    advance(system)
    assert state(client, mid)['status'] == 'completed'
    assert len(client.get('/api/events', params={'mission_id': mid}).json()) == 4


def test_cancel_between_read_and_send_prevents_movement(system):
    client, clock, _ = system
    mid = create(client)
    robot = client.get('/api/robots/robot-1').json()
    sample = next_sample(robot, state(client, mid), clock[0].isoformat())
    client.post(f'/api/missions/{mid}/cancel', json={'reason': 'Stop now'})
    assert client.post('/api/telemetry', json=sample).status_code == 409
    advance(system)
    assert state(client, mid)['status'] == 'cancelled'
    assert state(client, mid)['execution_step'] == 0
    assert client.get('/api/events', params={'mission_id': mid}).json() == []


def test_lost_ack_and_concurrent_steps_do_not_double_advance(system):
    client, clock, _ = system
    mid = create(client)
    robot = client.get('/api/robots/robot-1').json()
    sample = next_sample(robot, state(client, mid), clock[0].isoformat())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/telemetry', json=sample), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()['duplicate'] for r in responses) == 1
    sample['event_id'] = 'competing-worker'
    assert client.post('/api/telemetry', json=sample).status_code == 409
    assert state(client, mid)['execution_step'] == 1
    advance(system)
    assert state(client, mid)['execution_step'] == 2


def test_reject_skipped_waypoints_and_teleport(system):
    client, clock, _ = system
    mid = create(client)
    robot = client.get('/api/robots/robot-1').json()
    sample = next_sample(robot, state(client, mid), clock[0].isoformat())
    sample['position'] = {'x': 2, 'y': 2}
    sample['completed_waypoints'] = 2
    sample['mission_status'] = 'completed'
    assert client.post('/api/telemetry', json=sample).status_code == 422
    assert state(client, mid)['execution_step'] == 0
    assert client.get('/api/events', params={'mission_id': mid}).json() == []


def test_worker_never_executes_pending_or_timed_out_mission(system):
    client, clock, app = system
    pending = client.post('/api/missions', json={'robot_id': 'robot-1', 'waypoints': [{'x': 1, 'y': 0}]}).json()
    advance(system)
    assert state(client, pending['id'])['status'] == 'pending'
    client.post(f"/api/missions/{pending['id']}/approve")
    clock[0] += timedelta(seconds=16)
    app.state.check_disconnects()
    advance(system)
    assert state(client, pending['id'])['status'] == 'failed'
    assert state(client, pending['id'])['execution_step'] == 0


def test_repeated_and_negative_waypoints(system):
    client, _, _ = system
    mid = create(client, [{'x': 0, 'y': 0}, {'x': 0, 'y': 0}, {'x': -1, 'y': 0}])
    for _ in range(3):
        advance(system)
    assert state(client, mid)['status'] == 'completed'
    assert state(client, mid)['completed_waypoints'] == 3
    assert state(client, mid)['execution_position'] == {'x': -1, 'y': 0}
