"""Reliable ATLAS transport used by synthetic and future ROS 2 producers.

This module deliberately has no ROS dependency. A ROS 2 node can convert topic
messages into :class:`TelemetryEvent` objects while this layer owns identity,
durable buffering, retries, and the HTTP contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import httpx


@dataclass(frozen=True)
class TelemetryEvent:
    event_id: str
    robot_id: str
    occurred_at: str
    x: float
    y: float
    battery: float
    mission_id: str | None = None
    sensor_status: Literal["ok", "failed"] = "ok"
    navigation_status: Literal["ok", "failed"] = "ok"
    mission_status: Literal["running", "completed"] = "running"

    def __post_init__(self):
        if not self.event_id or len(self.event_id) > 128:
            raise ValueError("event_id must contain 1 to 128 characters")
        if not self.robot_id:
            raise ValueError("robot_id is required")
        if not all(math.isfinite(value) for value in (self.x, self.y, self.battery)):
            raise ValueError("position and battery must be finite")
        if not 0 <= self.battery <= 100:
            raise ValueError("battery must be between 0 and 100")

    def payload(self) -> dict:
        values = asdict(self)
        values["position"] = {"x": values.pop("x"), "y": values.pop("y")}
        return values


def ros_event_id(robot_id: str, stamp_nanoseconds: int, sequence: int = 0) -> str:
    """Create a stable, bounded ID so replaying one ROS observation is idempotent."""
    if stamp_nanoseconds < 0 or sequence < 0:
        raise ValueError("ROS timestamp and sequence must be non-negative")
    digest = hashlib.sha256(
        f"{robot_id}\0{stamp_nanoseconds}\0{sequence}".encode()
    ).hexdigest()[:24]
    return f"ros:{robot_id}:{stamp_nanoseconds}:{sequence}:{digest}"


@dataclass(frozen=True)
class FlushResult:
    delivered: int = 0
    quarantined: int = 0
    retained: int = 0


@dataclass(frozen=True)
class MissionCommand:
    action: Literal["start", "cancel"]
    mission: dict | None


class MissionCoordinator:
    """Deterministic mission/goal reconciliation independent of ROS callbacks."""

    def __init__(self):
        self.active: dict | None = None
        self.desired: dict | None = None
        self.cancelling = False
        self.terminal = False

    def reconcile(self, mission: dict | None) -> MissionCommand | None:
        self.desired = mission
        if self.cancelling:
            return None
        if self.active is None:
            if mission is None:
                return None
            self.active = mission
            self.terminal = False
            return MissionCommand("start", mission)
        if self.terminal:
            if mission and mission["id"] == self.active["id"]:
                return None
            self.active = mission
            self.terminal = False
            return MissionCommand("start", mission) if mission else None
        if mission and mission["id"] == self.active["id"]:
            return None
        self.cancelling = True
        return MissionCommand("cancel", self.active)

    def cancelled(self) -> MissionCommand | None:
        self.active = None
        self.cancelling = False
        self.terminal = False
        if self.desired is None:
            return None
        self.active = self.desired
        return MissionCommand("start", self.desired)

    def finished(self, mission_id: str) -> MissionCommand | None:
        if not self.active or self.active["id"] != mission_id:
            return None
        self.cancelling = False
        self.terminal = True
        if self.desired and self.desired["id"] != mission_id:
            self.active = self.desired
            self.terminal = False
            return MissionCommand("start", self.desired)
        return None


class TelemetryOutbox:
    """Small SQLite outbox that survives API and bridge process outages."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS telemetry_outbox (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS rejected_telemetry (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    rejected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def _connect(self):
        return self._connection

    def close(self):
        self._connection.close()

    def enqueue(self, event: TelemetryEvent):
        payload = json.dumps(event.payload(), sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM telemetry_outbox WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if existing and existing[0] != payload:
                raise ValueError("event_id is already queued with another payload")
            connection.execute(
                "INSERT OR IGNORE INTO telemetry_outbox(event_id, payload) VALUES (?, ?)",
                (event.event_id, payload),
            )

    def pending(self, limit: int = 100) -> list[tuple[str, dict]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, payload FROM telemetry_outbox "
                "ORDER BY queued_at, rowid LIMIT ?",
                (limit,),
            ).fetchall()
        return [(event_id, json.loads(payload)) for event_id, payload in rows]

    def count(self) -> int:
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0]

    def rejected_count(self) -> int:
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM rejected_telemetry").fetchone()[0]

    def acknowledge(self, event_id: str):
        with self._connect() as connection:
            connection.execute("DELETE FROM telemetry_outbox WHERE event_id = ?", (event_id,))

    def reject(self, event_id: str, payload: dict, reason: str):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO rejected_telemetry(event_id, payload, reason) "
                "VALUES (?, ?, ?)",
                (event_id, encoded, reason[:500]),
            )
            connection.execute("DELETE FROM telemetry_outbox WHERE event_id = ?", (event_id,))


class AtlasBridge:
    """Poll missions and deliver buffered telemetry through the ATLAS API."""

    def __init__(self, client, robot_id: str, api_key: str, outbox: TelemetryOutbox):
        if not robot_id or not api_key:
            raise ValueError("robot_id and api_key are required")
        self.client = client
        self.robot_id = robot_id
        self.api_key = api_key
        self.outbox = outbox

    def active_mission(self) -> dict | None:
        response = self.client.get(
            "/api/missions",
            params={"robot_id": self.robot_id, "status": "running", "limit": 2},
        )
        response.raise_for_status()
        missions = response.json()
        if len(missions) > 1:
            raise RuntimeError(f"robot {self.robot_id} has multiple running missions")
        return missions[0] if missions else None

    def submit(self, event: TelemetryEvent, limit: int = 100) -> FlushResult:
        if event.robot_id != self.robot_id:
            raise ValueError("event robot does not match bridge robot")
        self.outbox.enqueue(event)
        return self.flush(limit)

    def flush(self, limit: int = 100) -> FlushResult:
        delivered = quarantined = 0
        for event_id, payload in self.outbox.pending(limit):
            try:
                response = self.client.post(
                    "/api/telemetry",
                    json=payload,
                    headers={"X-ATLAS-Bridge-Key": self.api_key},
                )
            except httpx.TransportError:
                break
            if 200 <= response.status_code < 300:
                self.outbox.acknowledge(event_id)
                delivered += 1
                continue
            if response.status_code in (401, 403, 408, 429) or response.status_code >= 500:
                break
            self.outbox.reject(event_id, payload, f"HTTP {response.status_code}: {response.text}")
            quarantined += 1
        return FlushResult(delivered, quarantined, self.outbox.count())
