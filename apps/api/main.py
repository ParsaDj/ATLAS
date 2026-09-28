"""Local portfolio API. All operational data is synthetic."""
import asyncio
import os
import logging
import math
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, AwareDatetime, ConfigDict
from sqlalchemy import create_engine, String, JSON, select, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from apps.ai_agent.service import investigate as investigate_records
from apps.api.migrations import require_current_schema


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Robot(Base):
    __tablename__ = "robots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class Telemetry(Base):
    __tablename__ = "telemetry"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String, unique=True)
    data: Mapped[dict] = mapped_column(JSON)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class Sample(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    robot_id: str
    occurred_at: AwareDatetime
    position: Position
    battery: float = Field(ge=0, le=100)
    mission_id: str | None = None
    sensor_status: Literal["ok", "failed"] = "ok"
    mission_status: Literal["running", "completed"] = "running"
    execution_step: int | None = Field(default=None, ge=1)
    completed_waypoints: int | None = Field(default=None, ge=0)


class CancelRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class MissionRequest(StrictModel):
    robot_id: str
    waypoints: list[Position] = Field(min_length=1, max_length=100)


def create_app(database_url=None, clock=now, monitor=True):
    engine = create_engine(database_url or os.getenv("DATABASE_URL", "sqlite:///./atlas.db"))
    if engine.dialect.name == "sqlite":
        # SQLite has no row locks; serialize transactions for equivalent invariants.
        @event.listens_for(engine, "connect")
        def sqlite_connect(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA busy_timeout=10000")

        @event.listens_for(engine, "begin")
        def sqlite_begin(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    sessions = sessionmaker(engine, expire_on_commit=False)

    def seed_robots():
        with sessions.begin() as db:
            for n in range(1, 6):
                rid = f"robot-{n}"
                if not db.get(Robot, rid):
                    db.add(Robot(id=rid, data={"id": rid, "name": f"Robot {n}", "status": "unknown", "last_contact": None, "last_event_at": None, "battery": None, "position": None, "mission_id": None}))

    def incident(db, robot, mission_id, kind, event_id, timestamp):
        key = f"{mission_id}:{kind}" if mission_id else f"{robot.id}:{kind}:{event_id}"
        if db.scalar(select(Incident).where(Incident.dedup_key == key)):
            return
        iid = str(uuid4())
        db.add(Incident(id=iid, dedup_key=key, data={"id": iid, "robot_id": robot.id, "mission_id": mission_id, "type": kind, "status": "open", "event_ids": [event_id] if event_id else [], "detected_at": timestamp.isoformat(), "suspected_cause": kind, "resolution": None}))
        if mission_id:
            mission = db.get(Mission, mission_id)
            if mission and mission.data["status"] == "running":
                mission.data = {**mission.data, "status": "failed", "ended_at": timestamp.isoformat()}

    def check_disconnects():
        with sessions.begin() as db:
            for robot in db.scalars(select(Robot).with_for_update()):
                contact = robot.data["last_contact"]
                active = db.get(Mission, robot.data["mission_id"]) if robot.data["mission_id"] else None
                if active and active.data["status"] == "running":
                    contact = max(filter(None, [contact, active.data["started_at"]]))
                needs_check = robot.data["status"] != "disconnected" or (active and active.data["status"] == "running")
                if contact and needs_check and clock() - datetime.fromisoformat(contact) > timedelta(seconds=15):
                    incident(db, robot, robot.data["mission_id"], "disconnection", None, clock())
                    robot.data = {**robot.data, "status": "disconnected"}

    async def watchdog():
        while True:
            await asyncio.sleep(5)
            try:
                await asyncio.to_thread(check_disconnects)
            except Exception:
                logging.getLogger(__name__).exception("Heartbeat check failed; retrying next cycle")

    @asynccontextmanager
    async def lifespan(app):
        require_current_schema(engine)
        seed_robots()
        task = asyncio.create_task(watchdog()) if monitor else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            engine.dispose()

    app = FastAPI(title="ATLAS — Synthetic Fleet API", lifespan=lifespan)
    app.state.check_disconnects = check_disconnects

    def get_record(model, identifier):
        with sessions() as db:
            row = db.get(model, identifier)
            if not row:
                raise HTTPException(404, "Record not found")
            return row.data

    @app.get("/health")
    def health():
        with sessions() as db:
            db.execute(select(1))
        return {"status": "ok"}

    @app.get("/api/robots")
    def robots():
        with sessions() as db:
            return [r.data for r in db.scalars(select(Robot).order_by(Robot.id))]

    @app.get("/api/robots/{robot_id}")
    def robot(robot_id: str):
        return get_record(Robot, robot_id)

    def event_records(db, robot_id=None, mission_id=None, limit=100, offset=0):
        query = select(Telemetry)
        if robot_id is not None:
            query = query.where(Telemetry.data["robot_id"].as_string() == robot_id)
        if mission_id is not None:
            query = query.where(Telemetry.data["mission_id"].as_string() == mission_id)
        query = query.order_by(Telemetry.data["occurred_at"].as_string().desc(), Telemetry.id).limit(limit).offset(offset)
        return [r.data for r in db.scalars(query)]

    @app.get("/api/robots/{robot_id}/telemetry")
    def telemetry(robot_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        get_record(Robot, robot_id)
        with sessions() as db:
            return event_records(db, robot_id=robot_id, limit=limit, offset=offset)

    @app.get("/api/events")
    def events(robot_id: str | None = None, mission_id: str | None = None,
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        with sessions() as db:
            return event_records(db, robot_id, mission_id, limit, offset)

    @app.get("/api/events/{event_id}")
    def event_detail(event_id: str):
        return get_record(Telemetry, event_id)

    @app.get("/api/missions")
    def missions(robot_id: str | None = None,
                 status: Literal["pending", "running", "completed", "failed", "cancelled"] | None = None,
                 limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        with sessions() as db:
            query = select(Mission)
            if robot_id is not None:
                query = query.where(Mission.data["robot_id"].as_string() == robot_id)
            if status is not None:
                query = query.where(Mission.data["status"].as_string() == status)
            query = query.order_by(Mission.data["created_at"].as_string().desc(), Mission.id).limit(limit).offset(offset)
            return [m.data for m in db.scalars(query)]

    @app.post("/api/missions", status_code=201)
    def create_mission(body: MissionRequest):
        with sessions.begin() as db:
            if not db.get(Robot, body.robot_id):
                raise HTTPException(404, "Robot not found")
            mid = str(uuid4())
            data = {"id": mid, **body.model_dump(), "status": "pending", "created_at": clock().isoformat(), "started_at": None, "ended_at": None, "execution_step": 0, "completed_waypoints": 0}
            db.add(Mission(id=mid, data=data))
            return data

    @app.get("/api/missions/{mission_id}")
    def mission(mission_id: str):
        return get_record(Mission, mission_id)

    @app.post("/api/missions/{mission_id}/approve")
    def approve(mission_id: str):
        with sessions.begin() as db:
            m = db.get(Mission, mission_id)
            if not m:
                raise HTTPException(404, "Mission not found")
            r = db.scalar(select(Robot).where(Robot.id == m.data["robot_id"]).with_for_update())
            db.refresh(m)
            if m.data["status"] != "pending":
                raise HTTPException(409, "Only pending missions can be approved")
            previous = db.get(Mission, r.data["mission_id"]) if r.data["mission_id"] else None
            if previous and previous.data["status"] == "running":
                raise HTTPException(409, "Robot already has a running mission")
            m.data = {**m.data, "status": "running", "started_at": clock().isoformat(), "execution_position": r.data["position"] or {"x": 0.0, "y": 0.0}}
            r.data = {**r.data, "mission_id": m.id}
            return m.data

    @app.post("/api/missions/{mission_id}/cancel")
    def cancel(mission_id: str, body: CancelRequest):
        with sessions.begin() as db:
            m = db.get(Mission, mission_id)
            if not m:
                raise HTTPException(404, "Mission not found")
            db.scalar(select(Robot).where(Robot.id == m.data["robot_id"]).with_for_update())
            db.refresh(m)
            if m.data["status"] not in ("pending", "running"):
                raise HTTPException(409, "Only pending or running missions can be cancelled")
            m.data = {**m.data, "status": "cancelled", "ended_at": clock().isoformat(), "cancellation_reason": body.reason}
            return m.data

    @app.post("/api/telemetry")
    def ingest(body: Sample):
        timestamp = clock()
        if body.occurred_at > timestamp + timedelta(seconds=30):
            raise HTTPException(422, "Event timestamp is too far in the future")
        payload = body.model_dump(mode="json", exclude_none=True)
        payload["mission_id"] = body.mission_id
        payload["occurred_at"] = body.occurred_at.astimezone(timezone.utc).isoformat()
        try:
            with sessions.begin() as db:
                r = db.scalar(select(Robot).where(Robot.id == body.robot_id).with_for_update())
                if not r:
                    raise HTTPException(404, "Robot not found")
                existing = db.get(Telemetry, body.event_id)
                if existing:
                    if {k: v for k, v in existing.data.items() if k != "received_at"} != payload:
                        raise HTTPException(409, "Event ID reused with different payload")
                    return {"event_id": body.event_id, "duplicate": True}
                m = db.get(Mission, body.mission_id) if body.mission_id else None
                if body.mission_id and (not m or m.data["robot_id"] != r.id or m.data["started_at"] is None):
                    raise HTTPException(422, "Mission must exist, belong to robot and be approved")
                managed = body.execution_step is not None
                if managed or body.completed_waypoints is not None:
                    if not managed or body.completed_waypoints is None or not m:
                        raise HTTPException(422, "Execution requires mission, step and waypoint progress")
                    if m.data["status"] != "running" or r.data["mission_id"] != m.id:
                        raise HTTPException(409, "Mission is no longer running")
                    previous_step = m.data.get("execution_step", 0)
                    reached = m.data.get("completed_waypoints", 0)
                    if body.execution_step != previous_step + 1:
                        raise HTTPException(409, "Execution progress changed; reload mission")
                    if reached >= len(m.data["waypoints"]):
                        raise HTTPException(409, "All waypoints already reached")
                    origin = m.data.get("execution_position") or {"x": 0.0, "y": 0.0}
                    target = m.data["waypoints"][reached]
                    distance = math.hypot(target["x"] - origin["x"], target["y"] - origin["y"])
                    fraction = min(1.0, 1.0 / distance) if distance else 1.0
                    expected = {axis: origin[axis] + (target[axis] - origin[axis]) * fraction for axis in ("x", "y")}
                    if any(not math.isclose(getattr(body.position, axis), expected[axis], abs_tol=1e-8) for axis in ("x", "y")):
                        raise HTTPException(422, "Execution must advance at most one unit toward the next waypoint")
                    expected_reached = reached + (1 if distance <= 1.0 else 0)
                    if body.completed_waypoints != expected_reached:
                        raise HTTPException(422, "Invalid waypoint progress")
                    expected_status = "completed" if expected_reached == len(m.data["waypoints"]) else "running"
                    if body.mission_status != expected_status:
                        raise HTTPException(422, "Completion requires every waypoint")
                    if timestamp - body.occurred_at > timedelta(seconds=15) or (r.data["last_event_at"] and body.occurred_at <= datetime.fromisoformat(r.data["last_event_at"])):
                        raise HTTPException(409, "Execution telemetry is stale; reload mission")
                    m.data = {**m.data, "execution_step": body.execution_step, "completed_waypoints": body.completed_waypoints, "execution_position": payload["position"]}
                db.add(Telemetry(id=body.event_id, data={**payload, "received_at": timestamp.isoformat()}))
                fresh = not r.data["last_event_at"] or body.occurred_at > datetime.fromisoformat(r.data["last_event_at"])
                recent = timestamp - body.occurred_at <= timedelta(seconds=15)
                active = db.get(Mission, r.data["mission_id"]) if r.data["mission_id"] else None
                idle = body.mission_id is None and (not active or active.data["status"] != "running")
                if fresh and recent and (body.mission_id == r.data["mission_id"] or idle):
                    faults = []
                    if body.sensor_status == "failed":
                        faults.append("sensor_failure")
                    if body.battery < 20:
                        faults.append("low_battery")
                    r.data = {**r.data, "status": "attention" if faults else "online", "last_contact": timestamp.isoformat(), "last_event_at": payload["occurred_at"], "position": payload["position"], "battery": body.battery}
                    for fault in faults:
                        incident(db, r, body.mission_id, fault, body.event_id, timestamp)
                    if not faults and m and m.data["status"] == "running" and body.mission_status == "completed":
                        m.data = {**m.data, "status": "completed", "ended_at": timestamp.isoformat()}
                return {"event_id": body.event_id, "duplicate": False}
        except IntegrityError:
            with sessions() as db:
                existing = db.get(Telemetry, body.event_id)
                if existing and {k: v for k, v in existing.data.items() if k != "received_at"} == payload:
                    return {"event_id": body.event_id, "duplicate": True}
            raise HTTPException(409, "Concurrent update; retry the same event")

    @app.get("/api/incidents")
    def incidents(robot_id: str | None = None, mission_id: str | None = None,
                  limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        with sessions() as db:
            query = select(Incident)
            if robot_id is not None:
                query = query.where(Incident.data["robot_id"].as_string() == robot_id)
            if mission_id is not None:
                query = query.where(Incident.data["mission_id"].as_string() == mission_id)
            query = query.order_by(Incident.data["detected_at"].as_string().desc(), Incident.id).limit(limit).offset(offset)
            return [i.data for i in db.scalars(query)]

    @app.get("/api/incidents/{incident_id}")
    def incident_detail(incident_id: str):
        return get_record(Incident, incident_id)

    @app.post("/api/incidents/{incident_id}/investigate")
    def investigate_incident(incident_id: str):
        """Run a read-only, evidence-grounded investigation."""
        with sessions() as db:
            row = db.get(Incident, incident_id)
            if not row:
                raise HTTPException(404, "Incident not found")
            incident_data = row.data
            mission = (
                db.get(Mission, incident_data["mission_id"])
                if incident_data.get("mission_id")
                else None
            )
            event_ids = incident_data.get("event_ids", [])
            evidence = [db.get(Telemetry, event_id) for event_id in event_ids]
            events = [record.data for record in evidence if record is not None]
            return investigate_records(
                incident_data,
                mission.data if mission else None,
                events,
            )

    dashboard = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
    if dashboard.is_dir():
        app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")

    return app


app = create_app()
