"""Run ATLAS's portfolio failure story against a live API.

The default workflow stops at a draft maintenance ticket. Passing
--approve-maintenance is an explicit operator action; the investigator never
receives or invokes an approval tool.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from simulator.fleet import authenticate, send_event


TECHNICIAN = "demo-technician"
TECHNICIAN_PASSWORD = "atlas-demo-technician-password"


def _require(response: httpx.Response, context: str):
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise RuntimeError(f"{context}: {error.response.text}") from error
    return response.json()


def _ensure_technician(client: httpx.Client) -> None:
    users = _require(client.get("/api/users"), "cannot list demo users")
    if any(user["username"] == TECHNICIAN for user in users):
        return
    _require(
        client.post(
            "/api/users",
            json={
                "username": TECHNICIAN,
                "password": TECHNICIAN_PASSWORD,
                "role": "technician",
            },
        ),
        "cannot create demo technician",
    )


def execute_demo(
    client: httpx.Client,
    *,
    run_id: str,
    started_at: datetime,
    approve_maintenance: bool = False,
) -> dict:
    """Execute and verify the sensor-failure workflow through the real API."""
    _ensure_technician(client)
    mission = _require(
        client.post(
            "/api/missions",
            json={"robot_id": "robot-3", "waypoints": [{"x": 4, "y": 2}]},
        ),
        "cannot create Robot 3 mission",
    )
    mission = _require(
        client.post(f"/api/missions/{mission['id']}/approve"),
        "cannot approve Robot 3 mission",
    )

    healthy_event = {
        "event_id": f"demo:{run_id}:healthy",
        "robot_id": "robot-3",
        "mission_id": mission["id"],
        "occurred_at": started_at.isoformat(),
        "position": {"x": 1, "y": 1},
        "battery": 88,
        "sensor_status": "ok",
        "mission_status": "running",
    }
    failed_event = {
        **healthy_event,
        "event_id": f"demo:{run_id}:sensor-failed",
        "occurred_at": (started_at + timedelta(seconds=5)).isoformat(),
        "position": {"x": 2, "y": 1.5},
        "battery": 87,
        "sensor_status": "failed",
    }
    send_event(client, healthy_event, sleep=lambda _: None)
    send_event(client, failed_event, sleep=lambda _: None)

    failed_mission = _require(
        client.get(f"/api/missions/{mission['id']}"), "cannot load failed mission"
    )
    incidents = _require(
        client.get("/api/incidents", params={"mission_id": mission["id"]}),
        "cannot load incident",
    )
    if failed_mission["status"] != "failed" or len(incidents) != 1:
        raise RuntimeError("ATLAS did not converge to one failed mission and one incident")
    incident = incidents[0]
    if incident["type"] != "sensor_failure" or incident["event_ids"] != [failed_event["event_id"]]:
        raise RuntimeError("Incident evidence does not match the injected sensor failure")

    investigation = _require(
        client.post(f"/api/incidents/{incident['id']}/investigate"),
        "cannot investigate incident",
    )
    citation_ids = {citation["id"] for citation in investigation["citations"]}
    required_citations = {failed_event["event_id"], mission["id"], "DOC-SENSOR-001"}
    if not required_citations <= citation_ids:
        raise RuntimeError("Investigation omitted required evidence citations")

    ticket = _require(
        client.post(
            f"/api/incidents/{incident['id']}/tickets",
            json={
                "summary": "Inspect Robot 3 sensor path and run an authorized calibration check",
                "assigned_technician": TECHNICIAN,
            },
        ),
        "cannot create draft maintenance ticket",
    )
    if approve_maintenance:
        ticket = _require(
            client.post(f"/api/tickets/{ticket['id']}/approve"),
            "cannot approve maintenance ticket",
        )

    return {
        "run_id": run_id,
        "robot_id": "robot-3",
        "mission": {"id": mission["id"], "status": failed_mission["status"]},
        "injected_event_id": failed_event["event_id"],
        "incident": {
            "id": incident["id"],
            "type": incident["type"],
            "event_ids": incident["event_ids"],
        },
        "investigation": {
            "finding": investigation["finding"],
            "confidence": investigation["confidence"],
            "limitations": investigation["limitations"],
            "citations": investigation["citations"],
            "generated_by": investigation["generated_by"],
            "model": investigation.get("model"),
        },
        "maintenance_ticket": {
            "id": ticket["id"],
            "status": ticket["status"],
            "assigned_technician": ticket["assigned_technician"],
        },
    }


def print_story(result: dict) -> None:
    investigation = result["investigation"]
    print(f"[1/7] MISSION APPROVED     Robot 3 · {result['mission']['id']}")
    print(f"[2/7] FAILURE INJECTED    sensor_status=failed · {result['injected_event_id']}")
    print(f"[3/7] INCIDENT CREATED    {result['incident']['type']} · {result['incident']['id']}")
    print(f"[4/7] EVIDENCE CORRELATED {len(investigation['citations'])} exact citations")
    print(f"[5/7] INVESTIGATION       {investigation['confidence']} · {investigation['generated_by']}")
    print(f"      {investigation['finding']}")
    print(f"[6/7] LIMITATION          {investigation['limitations'][0]}")
    status = result["maintenance_ticket"]["status"]
    label = "HUMAN APPROVED" if status == "approved" else "HUMAN APPROVAL REQUIRED"
    print(f"[7/7] {label:<20} ticket {result['maintenance_ticket']['id']} · {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default=os.getenv("ATLAS_OPERATOR_USERNAME", "atlas-admin"))
    parser.add_argument("--password", default=os.getenv("ATLAS_OPERATOR_PASSWORD"))
    parser.add_argument("--bridge-key", default=os.getenv("ATLAS_TELEMETRY_API_KEY"))
    parser.add_argument(
        "--approve-maintenance",
        action="store_true",
        default=os.getenv("ATLAS_DEMO_APPROVE") == "1",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    with httpx.Client(base_url=args.url, timeout=30) as client:
        try:
            authenticate(client, args.username, args.password, args.bridge_key)
            result = execute_demo(
                client,
                run_id=str(uuid4()),
                started_at=datetime.now(timezone.utc),
                approve_maintenance=args.approve_maintenance,
            )
        except (RuntimeError, httpx.HTTPError) as error:
            raise SystemExit(f"ATLAS failure demo failed: {error}") from error

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print_story(result)


if __name__ == "__main__":
    main()
