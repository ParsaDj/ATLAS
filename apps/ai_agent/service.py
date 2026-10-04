"""Evidence-grounded incident investigation without a paid model.

The service accepts records already authorized and loaded by the API. It never
queries the database, changes operational state, or controls a robot. A future
LLM adapter can replace the renderer while keeping this evidence contract.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Guide:
    id: str
    title: str
    fault: str
    text: str
    next_step: str
    version: str = "1.0"
    checksum: str = ""


_DOCUMENTS = Path(__file__).with_name("documents")


def _guide(identifier: str, title: str, fault: str, filename: str, next_step: str) -> Guide:
    text = (_DOCUMENTS / filename).read_text()
    return Guide(identifier, title, fault, text, next_step, "1.0", sha256(text.encode()).hexdigest())


GUIDES = (
    _guide(
        "DOC-BATTERY-001",
        "Low battery during inspection",
        "low_battery",
        "low-battery.md",
        "Inspect the recent battery trend and charging history before approving another mission.",
    ),
    _guide(
        "DOC-SENSOR-001",
        "Inspection sensor failure",
        "sensor_failure",
        "sensor-failure.md",
        "Review the sensor observations and run a calibration check before rescheduling the inspection.",
    ),
    _guide(
        "DOC-CONNECTION-001",
        "Robot heartbeat loss",
        "disconnection",
        "heartbeat-loss.md",
        "Check the robot process and network path, then confirm a fresh heartbeat before creating a replacement mission.",
    ),
    _guide(
        "DOC-NAVIGATION-001",
        "Navigation action failure",
        "navigation_failure",
        "navigation-failure.md",
        "Review the Nav2 result and local costmap before approving a replacement mission.",
    ),
)


def retrieve_guides(fault: str) -> list[Guide]:
    """Return only approved troubleshooting material for the observed fault."""
    return [guide for guide in GUIDES if guide.fault == fault]


def investigate(
    incident: dict[str, Any],
    mission: dict[str, Any] | None,
    events: list[dict[str, Any]],
    guides: list[Guide] | None = None,
) -> dict[str, Any]:
    """Build a conservative finding from supplied read-only evidence."""
    guides = retrieve_guides(incident["type"]) if guides is None else guides
    referenced_ids = set(incident.get("event_ids", []))
    triggering = [event for event in events if event.get("event_id") in referenced_ids]
    citations: list[dict[str, str]] = []
    for event in triggering:
        citations.append({"type": "event", "id": event["event_id"]})
    if mission:
        citations.append({"type": "mission", "id": mission["id"]})
    for guide in guides:
        citations.append({
            "type": "document",
            "id": guide.id,
            "version": guide.version,
            "sha256": guide.checksum,
        })

    fault = incident["type"]
    robot = incident["robot_id"]
    mission_text = f" during mission {mission['id']}" if mission else ""
    limitations: list[str] = []
    confidence = "supported"

    if fault == "low_battery" and triggering:
        event = triggering[0]
        finding = (
            f"{robot} reported {event['battery']:g}% battery{mission_text}. "
            "The available record supports a low-battery mission failure."
        )
        limitations.append("The records do not establish battery health or why the charge was low.")
    elif fault == "sensor_failure" and triggering:
        finding = (
            f"{robot} reported a failed sensor status{mission_text}. "
            "The available record supports a sensor-path mission failure."
        )
        limitations.append("The records do not distinguish hardware, calibration, obstruction, or communication causes.")
    elif fault == "disconnection":
        finding = (
            f"{robot} stopped reporting heartbeats{mission_text}. "
            "The monitor detected loss of contact, but no telemetry event identifies the underlying cause."
        )
        limitations.append("No triggering telemetry record exists for a heartbeat timeout.")
        confidence = "limited"
    elif fault == "navigation_failure" and triggering:
        finding = (
            f"{robot} reported a failed navigation action{mission_text}. "
            "The available record supports a navigation mission failure."
        )
        limitations.append(
            "The bridge status does not establish whether planning, control, localization, or an obstacle caused the failure."
        )
    else:
        finding = f"The available records do not support a specific explanation for incident {incident['id']}."
        limitations.append("No recognized fault guide and triggering evidence were available.")
        confidence = "insufficient"

    if referenced_ids and not triggering:
        finding = f"The investigation cannot verify the triggering evidence for incident {incident['id']}."
        limitations.append("One or more event references are missing from the available records.")
        confidence = "insufficient"

    recommendation = (
        guides[0].next_step
        if guides
        else "Collect the missing operational records before taking maintenance action."
    )
    return {
        "incident_id": incident["id"],
        "finding": finding,
        "confidence": confidence,
        "limitations": limitations,
        "recommended_next_step": recommendation,
        "citations": citations,
        "tool_trace": [
            {"tool": "get_incident", "resource_id": incident["id"]},
            *([{"tool": "get_mission", "resource_id": mission["id"]}] if mission else []),
            {"tool": "list_incident_events", "resource_id": incident["id"]},
            *[
                {"tool": "retrieve_document", "resource_id": guide.id}
                for guide in guides
            ],
        ],
        "generated_by": "atlas-evidence-engine-v1",
    }
