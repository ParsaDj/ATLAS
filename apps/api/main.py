"""Local portfolio API. All operational data is synthetic."""
import asyncio
import base64
import hashlib
import hmac
import os
import logging
import math
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, AwareDatetime, ConfigDict
from sqlalchemy import Boolean, ForeignKey, create_engine, String, JSON, select, event
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


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String, index=True)
    resource_type: Mapped[str] = mapped_column(String)
    resource_id: Mapped[str] = mapped_column(String, index=True)
    occurred_at: Mapped[str] = mapped_column(String, index=True)
    details: Mapped[dict] = mapped_column(JSON)


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


Role = Literal["operator", "technician", "administrator"]


class LoginRequest(StrictModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=200)


class UserRequest(LoginRequest):
    role: Role


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def password_matches(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt, expected = encoded.split("$")
        derived = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(derived, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


def create_app(
    database_url=None,
    clock=now,
    monitor=True,
    bootstrap_admin_password=None,
    bootstrap_admin_username=None,
    telemetry_api_key=None,
):
    engine = create_engine(database_url or os.getenv("DATABASE_URL", "sqlite:///./atlas.db"))
    if engine.dialect.name == "sqlite":
        # SQLite has no row locks; serialize transactions for equivalent invariants.
        @event.listens_for(engine, "connect")
        def sqlite_connect(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA foreign_keys=ON")

        @event.listens_for(engine, "begin")
        def sqlite_begin(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    sessions = sessionmaker(engine, expire_on_commit=False)
    bridge_key = telemetry_api_key or os.getenv("ATLAS_TELEMETRY_API_KEY")
    if bridge_key and len(bridge_key) < 24:
        raise ValueError("ATLAS_TELEMETRY_API_KEY must contain at least 24 characters")

    def authorize_bridge(x_atlas_bridge_key: str | None = Header(default=None)):
        if not bridge_key:
            raise HTTPException(503, "Telemetry ingestion is not configured")
        if not x_atlas_bridge_key or not hmac.compare_digest(
            x_atlas_bridge_key.encode(), bridge_key.encode()
        ):
            raise HTTPException(401, "Invalid bridge credentials")

    def seed_robots():
        with sessions.begin() as db:
            for n in range(1, 6):
                rid = f"robot-{n}"
                if not db.get(Robot, rid):
                    db.add(Robot(id=rid, data={"id": rid, "name": f"Robot {n}", "status": "unknown", "last_contact": None, "last_event_at": None, "battery": None, "position": None, "mission_id": None}))

    def seed_admin():
        with sessions.begin() as db:
            if db.scalar(select(User.id).limit(1)):
                return
            password = bootstrap_admin_password or os.getenv("ATLAS_BOOTSTRAP_ADMIN_PASSWORD")
            if not password or len(password) < 12:
                raise RuntimeError(
                    "No users exist. Set ATLAS_BOOTSTRAP_ADMIN_PASSWORD to at least "
                    "12 characters before starting ATLAS."
                )
            username = bootstrap_admin_username or os.getenv(
                "ATLAS_BOOTSTRAP_ADMIN_USERNAME", "atlas-admin"
            )
            try:
                credentials = LoginRequest(username=username, password=password)
            except ValueError as error:
                raise RuntimeError(
                    "Bootstrap administrator credentials do not meet the login requirements."
                ) from error
            db.add(
                User(
                    id=str(uuid4()),
                    username=credentials.username,
                    password_hash=password_hash(credentials.password),
                    role="administrator",
                    active=True,
                )
            )

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
        seed_admin()
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

    def audit(db, actor_id, action, resource_type, resource_id, details=None):
        db.add(
            AuditLog(
                id=str(uuid4()),
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                occurred_at=clock().isoformat(),
                details=details or {},
            )
        )

    def actor_from_request(request: Request):
        token = request.cookies.get("atlas_session")
        if not token:
            raise HTTPException(401, "Authentication required")
        token_digest = hashlib.sha256(token.encode()).hexdigest()
        with sessions.begin() as db:
            session = db.get(AuthSession, token_digest)
            if not session or datetime.fromisoformat(session.expires_at) <= clock():
                if session:
                    db.delete(session)
                raise HTTPException(401, "Session expired or invalid")
            user = db.get(User, session.user_id)
            if not user or not user.active:
                raise HTTPException(401, "Account is inactive")
            return {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "token_hash": token_digest,
                "csrf_hash": session.csrf_hash,
            }

    def authorize(*roles, csrf=False):
        def dependency(request: Request):
            actor = actor_from_request(request)
            if roles and actor["role"] not in roles:
                raise HTTPException(403, "This role cannot perform that action")
            if csrf:
                supplied = request.headers.get("X-CSRF-Token", "")
                digest = hashlib.sha256(supplied.encode()).hexdigest()
                if not supplied or not hmac.compare_digest(digest, actor["csrf_hash"]):
                    raise HTTPException(403, "CSRF token is missing or invalid")
            return actor

        return dependency

    any_user = authorize()
    any_write = authorize("operator", "technician", "administrator", csrf=True)
    mission_write = authorize("operator", "administrator", csrf=True)
    admin_read = authorize("administrator")
    admin_write = authorize("administrator", csrf=True)

    @app.post("/api/auth/login")
    def login(body: LoginRequest, response: Response):
        with sessions.begin() as db:
            user = db.scalar(select(User).where(User.username == body.username))
            if not user or not user.active or not password_matches(body.password, user.password_hash):
                raise HTTPException(401, "Invalid username or password")
            token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            expires = clock() + timedelta(hours=8)
            db.add(
                AuthSession(
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    user_id=user.id,
                    csrf_hash=hashlib.sha256(csrf_token.encode()).hexdigest(),
                    expires_at=expires.isoformat(),
                )
            )
            audit(db, user.id, "auth.login", "user", user.id)
            response.set_cookie(
                "atlas_session",
                token,
                max_age=8 * 60 * 60,
                httponly=True,
                samesite="strict",
                secure=os.getenv("ATLAS_SECURE_COOKIES") == "1",
            )
            return {
                "user": {"id": user.id, "username": user.username, "role": user.role},
                "csrf_token": csrf_token,
            }

    @app.get("/api/auth/me")
    def me(actor=Depends(any_user)):
        return {key: actor[key] for key in ("id", "username", "role")}

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response, actor=Depends(any_write)):
        with sessions.begin() as db:
            session = db.get(AuthSession, actor["token_hash"])
            if session:
                db.delete(session)
            audit(db, actor["id"], "auth.logout", "user", actor["id"])
        response.delete_cookie("atlas_session")

    @app.post("/api/users", status_code=201)
    def create_user(body: UserRequest, actor=Depends(admin_write)):
        with sessions.begin() as db:
            if db.scalar(select(User).where(User.username == body.username)):
                raise HTTPException(409, "Username already exists")
            user = User(
                id=str(uuid4()),
                username=body.username,
                password_hash=password_hash(body.password),
                role=body.role,
                active=True,
            )
            db.add(user)
            audit(db, actor["id"], "user.create", "user", user.id, {"role": user.role})
            return {"id": user.id, "username": user.username, "role": user.role, "active": True}

    @app.get("/api/users")
    def users(_actor=Depends(admin_read)):
        with sessions() as db:
            return [
                {"id": user.id, "username": user.username, "role": user.role, "active": user.active}
                for user in db.scalars(select(User).order_by(User.username))
            ]

    @app.get("/api/audit-logs")
    def audit_logs(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        _actor=Depends(admin_read),
    ):
        with sessions() as db:
            rows = db.scalars(
                select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id).limit(limit).offset(offset)
            )
            result = []
            for row in rows:
                user = db.get(User, row.actor_id) if row.actor_id else None
                result.append(
                    {
                        "id": row.id,
                        "actor_id": row.actor_id,
                        "actor_username": user.username if user else "system",
                        "action": row.action,
                        "resource_type": row.resource_type,
                        "resource_id": row.resource_id,
                        "occurred_at": row.occurred_at,
                        "details": row.details,
                    }
                )
            return result

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
    def create_mission(body: MissionRequest, actor=Depends(mission_write)):
        with sessions.begin() as db:
            if not db.get(Robot, body.robot_id):
                raise HTTPException(404, "Robot not found")
            mid = str(uuid4())
            data = {"id": mid, **body.model_dump(), "status": "pending", "created_at": clock().isoformat(), "started_at": None, "ended_at": None, "execution_step": 0, "completed_waypoints": 0}
            db.add(Mission(id=mid, data=data))
            audit(db, actor["id"], "mission.create", "mission", mid, {"robot_id": body.robot_id, "waypoint_count": len(body.waypoints)})
            return data

    @app.get("/api/missions/{mission_id}")
    def mission(mission_id: str):
        return get_record(Mission, mission_id)

    @app.post("/api/missions/{mission_id}/approve")
    def approve(mission_id: str, actor=Depends(mission_write)):
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
            audit(db, actor["id"], "mission.approve", "mission", m.id, {"robot_id": r.id})
            return m.data

    @app.post("/api/missions/{mission_id}/cancel")
    def cancel(mission_id: str, body: CancelRequest, actor=Depends(mission_write)):
        with sessions.begin() as db:
            m = db.get(Mission, mission_id)
            if not m:
                raise HTTPException(404, "Mission not found")
            db.scalar(select(Robot).where(Robot.id == m.data["robot_id"]).with_for_update())
            db.refresh(m)
            if m.data["status"] not in ("pending", "running"):
                raise HTTPException(409, "Only pending or running missions can be cancelled")
            m.data = {**m.data, "status": "cancelled", "ended_at": clock().isoformat(), "cancellation_reason": body.reason}
            audit(db, actor["id"], "mission.cancel", "mission", m.id, {"reason": body.reason})
            return m.data

    @app.post("/api/telemetry")
    def ingest(body: Sample, _bridge=Depends(authorize_bridge)):
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
    def investigate_incident(incident_id: str, actor=Depends(any_write)):
        """Run a read-only, evidence-grounded investigation."""
        with sessions.begin() as db:
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
            result = investigate_records(
                incident_data,
                mission.data if mission else None,
                events,
            )
            audit(
                db,
                actor["id"],
                "incident.investigate",
                "incident",
                incident_id,
                {"confidence": result["confidence"]},
            )
            return result

    dashboard = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
    if dashboard.is_dir():
        app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")

    return app


app = create_app()
