"""Execute approved missions, recovering progress from the API on every tick.

Run one worker per facility. Optimistic execution steps protect against duplicate
workers and lost acknowledgements. Motion is synthetic: one unit per tick.
"""
import argparse
import logging
import math
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from simulator.fleet import send_event


def next_sample(robot, mission, timestamp):
    origin = mission.get('execution_position') or {'x': 0.0, 'y': 0.0}
    reached = mission.get('completed_waypoints', 0)
    target = mission['waypoints'][reached]
    distance = math.hypot(target['x'] - origin['x'], target['y'] - origin['y'])
    fraction = min(1.0, 1.0 / distance) if distance else 1.0
    position = {axis: origin[axis] + (target[axis] - origin[axis]) * fraction for axis in ('x', 'y')}
    reached += int(distance <= 1.0)
    step = mission.get('execution_step', 0) + 1
    return {'event_id': f"execution:{mission['id']}:{step}", 'robot_id': robot['id'],
            'mission_id': mission['id'], 'occurred_at': timestamp, 'position': position,
            'battery': 100, 'sensor_status': 'ok', 'execution_step': step,
            'completed_waypoints': reached,
            'mission_status': 'completed' if reached == len(mission['waypoints']) else 'running'}


def tick(client, clock=lambda: datetime.now(timezone.utc)):
    response = client.get('/api/robots')
    response.raise_for_status()
    for robot in response.json():
        try:
            mission = None
            if robot['mission_id']:
                response = client.get(f"/api/missions/{robot['mission_id']}")
                response.raise_for_status()
                mission = response.json()
            timestamp = clock().isoformat()
            if mission and mission['status'] == 'running':
                sample = next_sample(robot, mission, timestamp)
            else:
                sample = {'event_id': str(uuid4()), 'robot_id': robot['id'], 'mission_id': None,
                          'occurred_at': timestamp, 'position': robot['position'] or {'x': 0, 'y': 0},
                          'battery': 100, 'sensor_status': 'ok'}
            send_event(client, sample)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 409:
                raise
            # Cancellation, another worker, or changed progress. Re-read next tick.
            logging.info('Robot %s changed while processing; retrying next tick', robot['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or not 0.1 <= args.interval <= 5:
        parser.error('--interval must be between 0.1 and 5 seconds')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    with httpx.Client(base_url=args.url, timeout=5) as client:
        logging.info('ATLAS worker ready. Approve a mission in the dashboard. Ctrl+C stops the worker.')
        try:
            while True:
                try:
                    tick(client)
                except httpx.HTTPError as error:
                    logging.warning('API unavailable: %s. Retrying next tick.', error)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logging.info('Worker stopped. Saved mission progress remains in the API.')


if __name__ == '__main__':
    main()
