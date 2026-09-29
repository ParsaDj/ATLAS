"""Deterministic five-robot synthetic demo; no model API or ROS required."""
import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx


def sample(robot, mission, tick, run_id, timestamp):
    return {"event_id": f"{run_id}:{robot}:{tick}", "robot_id": robot,
            "mission_id": mission, "occurred_at": timestamp,
            "position": {"x": float(tick), "y": float(robot[-1])},
            "battery": 12 if robot == "robot-2" and tick >= 3 else max(30, 100-tick),
            "sensor_status": "failed" if robot == "robot-3" and tick >= 3 else "ok",
            "mission_status": "completed" if tick >= 7 else "running"}


def send_event(client, event, sleep=time.sleep):
    """Retry transient failures with the identical event ID and payload."""
    for attempt in range(3):
        try:
            response = client.post("/api/telemetry", json=event)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in (408, 429) and error.response.status_code < 500:
                raise
            if attempt == 2:
                raise
        except httpx.TransportError:
            if attempt == 2:
                raise
        sleep(2 ** attempt)


def prepare_fleet(client):
    response = client.get("/health")
    response.raise_for_status()
    response = client.get("/api/missions", params={"status": "running"})
    response.raise_for_status()
    if response.json():
        raise RuntimeError("Running missions already exist. Cancel them through /api/missions/{id}/cancel before restarting the demo.")
    missions = {}
    for n in range(1, 6):
        robot = f"robot-{n}"
        response = client.post("/api/missions", json={"robot_id": robot, "waypoints": [{"x": 7, "y": n}]})
        response.raise_for_status()
        missions[robot] = response.json()["id"]
        response = client.post(f"/api/missions/{missions[robot]}/approve")
        response.raise_for_status()
    return missions


def authenticate(client, username, password, bridge_key):
    if not password:
        raise RuntimeError("Set ATLAS_OPERATOR_PASSWORD or pass --password")
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    if not bridge_key:
        raise RuntimeError("Set ATLAS_TELEMETRY_API_KEY or pass --bridge-key")
    client.headers["X-ATLAS-Bridge-Key"] = bridge_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--ticks", type=int, default=10)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--output", default="events.jsonl")
    parser.add_argument("--username", default=os.getenv("ATLAS_OPERATOR_USERNAME", "atlas-admin"))
    parser.add_argument("--password", default=os.getenv("ATLAS_OPERATOR_PASSWORD"))
    parser.add_argument("--bridge-key", default=os.getenv("ATLAS_TELEMETRY_API_KEY"))
    args = parser.parse_args()
    if args.ticks < 1:
        parser.error("--ticks must be positive")
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("--interval must be finite and positive")
    run_id = str(uuid4())
    with httpx.Client(base_url=args.url, timeout=10) as client, open(args.output, "a") as output:
        try:
            authenticate(client, args.username, args.password, args.bridge_key)
            missions = prepare_fleet(client)
        except (RuntimeError, httpx.HTTPError) as error:
            raise SystemExit(f"Cannot start fleet: {error}") from error
        for tick in range(args.ticks):
            for robot, mission in missions.items():
                if robot == "robot-4" and tick >= 3:
                    continue  # Real missing heartbeat; watchdog detects disconnection.
                event = sample(robot, mission, tick, run_id, datetime.now(timezone.utc).isoformat())
                output.write(json.dumps(event) + "\n")
                output.flush()
                send_event(client, event)
            print(f"tick {tick + 1}/{args.ticks}", flush=True)
            time.sleep(args.interval)
        response = client.get("/api/incidents")
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
