"""Local portfolio API. All operational data is synthetic."""
import asyncio
import base64
import hashlib
import hmac
import os
import logging
import math
import secrets
from collections import Counter
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
from pathlib import Path
from time import monotonic

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, AwareDatetime, ConfigDict
from sqlalchemy import Boolean, ForeignKey, Index, create_engine, String, Text, JSON, select, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from apps.ai_agent.service import GUIDES, Guide, investigate as investigate_records
from apps.api.migrations import require_current_schema
from apps.api.observability import Metrics, install_observability, tracer_provider
from apps.api.reports import incident_report, mission_report
from apps.api.security import LoginRateLimiter


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
    __table_args__ = (
        Index("ix_missions_robot_created", "robot_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    source_incident_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        Index("ix_telemetry_robot_occurred", "robot_id", "occurred_at"),
        Index("ix_telemetry_mission_occurred", "mission_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), nullable=True, index=True)
    occurred_at: Mapped[str] = mapped_column(String, index=True)
    received_at: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_robot_detected", "robot_id", "detected_at"),
        Index("ix_incidents_mission_detected", "mission_id", "detected_at"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String, unique=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), nullable=True, index=True)
    fault_type: Mapped[str] = mapped_column(String, index=True)
    detected_at: Mapped[str] = mapped_column(String, index=True)
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


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id"), unique=True, index=True
    )
    assigned_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class TechnicalDocument(Base):
    __tablename__ = "technical_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    fault: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    next_step: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String)
    approved: Mapped[bool] = mapped_column(Boolean, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)


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
    navigation_status: Literal["ok", "failed"] = "ok"
    mission_status: Literal["running", "completed"] = "running"
    execution_step: int | None = Field(default=None, ge=1)
    completed_waypoints: int | None = Field(default=None, ge=0)


class CancelRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class MissionRequest(StrictModel):
    robot_id: str
    waypoints: list[Position] = Field(min_length=1, max_length=100)


class ReplacementMissionRequest(StrictModel):
    waypoints: list[Position] = Field(min_length=1, max_length=100)


Role = Literal["operator", "technician", "administrator"]


class LoginRequest(StrictModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=200)


class UserRequest(LoginRequest):
    role: Role


class TicketRequest(StrictModel):
    summary: str = Field(min_length=3, max_length=500, pattern=r"\S")
    assigned_technician: str = Field(
        min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$"
    )


class TicketResolution(StrictModel):
    resolution: str = Field(min_length=3, max_length=2000, pattern=r"\S")


class TechnicalDocumentRequest(StrictModel):
    id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Z0-9-]+$")
    version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+(?:\.[0-9]+){0,2}$")
    fault: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=3, max_length=200, pattern=r"\S")
    content: str = Field(min_length=20, max_length=100_000, pattern=r"\S")
    next_step: str = Field(min_length=3, max_length=1000, pattern=r"\S")


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
    otlp_endpoint=None,
    request_log=None,
    security_clock=None,
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
    metrics_registry = Metrics()
    tracing = tracer_provider(otlp_endpoint)
    login_limiter = LoginRateLimiter(time_source=security_clock or monotonic)
    dummy_password = password_hash(secrets.token_urlsafe(24))
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

    def seed_documents():
        with sessions.begin() as db:
            for guide in GUIDES:
                if not db.get(TechnicalDocument, (guide.id, guide.version)):
                    db.add(
                        TechnicalDocument(
                            id=guide.id,
                            version=guide.version,
                            fault=guide.fault,
                            title=guide.title,
                            content=guide.text,
                            next_step=guide.next_step,
                            checksum=guide.checksum,
                            approved=True,
                            created_at=clock().isoformat(),
                        )
                    )

    def incident(db, robot, mission_id, kind, event_id, timestamp):
        key = f"{mission_id}:{kind}" if mission_id else f"{robot.id}:{kind}:{event_id}"
        if db.scalar(select(Incident).where(Incident.dedup_key == key)):
            return
        iid = str(uuid4())
        detected_at = timestamp.isoformat()
        db.add(Incident(id=iid, dedup_key=key, robot_id=robot.id, mission_id=mission_id, fault_type=kind, detected_at=detected_at, data={"id": iid, "robot_id": robot.id, "mission_id": mission_id, "type": kind, "status": "open", "event_ids": [event_id] if event_id else [], "detected_at": detected_at, "suspected_cause": kind, "resolution": None}))
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
        seed_documents()
        task = asyncio.create_task(watchdog()) if monitor else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            engine.dispose()
            tracing.shutdown()

    app = FastAPI(title="ATLAS — Synthetic Fleet API", lifespan=lifespan)
    install_observability(app, tracing, metrics_registry, request_log)
    app.state.check_disconnects = check_disconnects
    app.state.metrics = metrics_registry

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

    def document_data(row):
        return {
            "id": row.id,
            "version": row.version,
            "fault": row.fault,
            "title": row.title,
            "content": row.content,
            "next_step": row.next_step,
            "sha256": row.checksum,
            "approved": row.approved,
            "created_at": row.created_at,
        }

    def investigation_guides(db, fault):
        rows = list(
            db.scalars(
                select(TechnicalDocument)
                .where(TechnicalDocument.fault == fault, TechnicalDocument.approved.is_(True))
                .order_by(TechnicalDocument.id, TechnicalDocument.created_at.desc(), TechnicalDocument.version.desc())
            )
        )
        latest = {}
        for row in rows:
            latest.setdefault(row.id, row)
        return [
            Guide(row.id, row.title, row.fault, row.content, row.next_step, row.version, row.checksum)
            for row in latest.values()
        ]

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
    ticket_create = authorize("operator", "administrator", csrf=True)
    ticket_work = authorize("technician", "administrator", csrf=True)

    @app.post("/api/auth/login")
    def login(body: LoginRequest, response: Response, request: Request):
        client_id = request.client.host if request.client else "unknown"
        retry_after = login_limiter.retry_after(client_id)
        if retry_after:
            raise HTTPException(
                429,
                "Too many login attempts; try again later",
                headers={"Retry-After": str(retry_after)},
            )
        with sessions.begin() as db:
            user = db.scalar(select(User).where(User.username == body.username))
            candidate_hash = user.password_hash if user and user.active else dummy_password
            password_valid = password_matches(body.password, candidate_hash)
            if not user or not user.active or not password_valid:
                login_limiter.failed(client_id)
                raise HTTPException(401, "Invalid username or password")
            login_limiter.succeeded(client_id)
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

    @app.get("/api/documents")
    def documents(
        fault: str | None = None,
        approved: bool | None = True,
        actor=Depends(any_user),
    ):
        if approved is not True and actor["role"] != "administrator":
            raise HTTPException(403, "Only administrators can view unapproved revisions")
        with sessions() as db:
            query = select(TechnicalDocument)
            if fault is not None:
                query = query.where(TechnicalDocument.fault == fault)
            if approved is not None:
                query = query.where(TechnicalDocument.approved.is_(approved))
            query = query.order_by(
                TechnicalDocument.id,
                TechnicalDocument.created_at.desc(),
                TechnicalDocument.version.desc(),
            )
            return [document_data(row) for row in db.scalars(query)]

    @app.get("/api/documents/{document_id}/versions/{version}")
    def document_revision(document_id: str, version: str, actor=Depends(any_user)):
        with sessions() as db:
            row = db.get(TechnicalDocument, (document_id, version))
            if not row:
                raise HTTPException(404, "Technical document revision not found")
            if not row.approved and actor["role"] != "administrator":
                raise HTTPException(403, "Only administrators can view unapproved revisions")
            return document_data(row)

    @app.post("/api/documents", status_code=201)
    def create_document(body: TechnicalDocumentRequest, actor=Depends(admin_write)):
        content = body.content.strip()
        checksum = hashlib.sha256(content.encode()).hexdigest()
        with sessions.begin() as db:
            if db.get(TechnicalDocument, (body.id, body.version)):
                raise HTTPException(409, "Technical document revision already exists")
            row = TechnicalDocument(
                id=body.id,
                version=body.version,
                fault=body.fault,
                title=body.title.strip(),
                content=content,
                next_step=body.next_step.strip(),
                checksum=checksum,
                approved=False,
                created_at=clock().isoformat(),
            )
            db.add(row)
            audit(
                db,
                actor["id"],
                "document.create_revision",
                "technical_document",
                body.id,
                {
                    "version": body.version,
                    "fault": body.fault,
                    "approved": False,
                    "sha256": checksum,
                },
            )
            return document_data(row)

    @app.post("/api/documents/{document_id}/versions/{version}/approve")
    def approve_document(document_id: str, version: str, actor=Depends(admin_write)):
        with sessions.begin() as db:
            row = db.scalar(
                select(TechnicalDocument)
                .where(
                    TechnicalDocument.id == document_id,
                    TechnicalDocument.version == version,
                )
                .with_for_update()
            )
            if not row:
                raise HTTPException(404, "Technical document revision not found")
            if row.approved:
                raise HTTPException(409, "Technical document revision is already approved")
            row.approved = True
            audit(
                db,
                actor["id"],
                "document.approve_revision",
                "technical_document",
                document_id,
                {"version": version, "sha256": row.checksum},
            )
            return document_data(row)

    def ticket_data(db, ticket):
        assigned = db.get(User, ticket.assigned_user_id)
        return {
            **ticket.data,
            "assigned_technician": assigned.username if assigned else "unavailable",
        }

    @app.post("/api/incidents/{incident_id}/tickets", status_code=201)
    def create_ticket(
        incident_id: str, body: TicketRequest, actor=Depends(ticket_create)
    ):
        with sessions.begin() as db:
            linked_incident = db.get(Incident, incident_id)
            if not linked_incident:
                raise HTTPException(404, "Incident not found")
            if linked_incident.data["status"] != "open":
                raise HTTPException(409, "Tickets require an open incident")
            if db.scalar(
                select(MaintenanceTicket).where(
                    MaintenanceTicket.incident_id == incident_id
                )
            ):
                raise HTTPException(409, "Incident already has a maintenance ticket")
            assigned = db.scalar(
                select(User).where(User.username == body.assigned_technician)
            )
            if not assigned or not assigned.active or assigned.role != "technician":
                raise HTTPException(422, "Assigned technician must be an active technician")
            ticket_id = str(uuid4())
            data = {
                "id": ticket_id,
                "incident_id": incident_id,
                "summary": body.summary,
                "status": "draft",
                "created_at": clock().isoformat(),
                "created_by": actor["username"],
                "approved_at": None,
                "approved_by": None,
                "started_at": None,
                "resolved_at": None,
                "resolution": None,
            }
            ticket = MaintenanceTicket(
                id=ticket_id,
                incident_id=incident_id,
                assigned_user_id=assigned.id,
                data=data,
            )
            db.add(ticket)
            audit(
                db,
                actor["id"],
                "ticket.create",
                "maintenance_ticket",
                ticket_id,
                {"incident_id": incident_id, "assigned_technician": assigned.username},
            )
            return {**data, "assigned_technician": assigned.username}

    @app.post("/api/incidents/{incident_id}/replacement-missions", status_code=201)
    def propose_replacement_mission(
        incident_id: str,
        body: ReplacementMissionRequest,
        actor=Depends(mission_write),
    ):
        with sessions.begin() as db:
            incident_row = db.scalar(
                select(Incident).where(Incident.id == incident_id).with_for_update()
            )
            if not incident_row:
                raise HTTPException(404, "Incident not found")
            source_id = incident_row.data.get("mission_id")
            source = db.get(Mission, source_id) if source_id else None
            if not source or source.data["status"] != "failed":
                raise HTTPException(409, "Replacement requires a failed source mission")
            existing = list(
                db.scalars(
                    select(Mission).where(
                        Mission.source_incident_id == incident_id
                    )
                )
            )
            if any(
                mission.data["status"] in ("pending", "running", "completed")
                for mission in existing
            ):
                raise HTTPException(409, "Incident already has an active replacement")
            mission_id = str(uuid4())
            data = {
                "id": mission_id,
                "robot_id": source.data["robot_id"],
                "waypoints": [point.model_dump() for point in body.waypoints],
                "status": "pending",
                "created_at": clock().isoformat(),
                "started_at": None,
                "ended_at": None,
                "execution_step": 0,
                "completed_waypoints": 0,
                "source_incident_id": incident_id,
                "replacement_for_mission_id": source.id,
                "proposed_by": actor["username"],
            }
            db.add(Mission(id=mission_id, robot_id=data["robot_id"], created_at=data["created_at"], source_incident_id=incident_id, data=data))
            audit(
                db,
                actor["id"],
                "mission.replacement_propose",
                "mission",
                mission_id,
                {
                    "source_incident_id": incident_id,
                    "replacement_for_mission_id": source.id,
                    "waypoint_count": len(body.waypoints),
                },
            )
            return data

    @app.get("/api/tickets")
    def tickets(
        incident_id: str | None = None,
        status: Literal["draft", "approved", "in_progress", "resolved"] | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        _actor=Depends(any_user),
    ):
        with sessions() as db:
            query = select(MaintenanceTicket)
            if incident_id is not None:
                query = query.where(MaintenanceTicket.incident_id == incident_id)
            if status is not None:
                query = query.where(
                    MaintenanceTicket.data["status"].as_string() == status
                )
            query = query.order_by(
                MaintenanceTicket.data["created_at"].as_string().desc(),
                MaintenanceTicket.id,
            ).limit(limit).offset(offset)
            return [ticket_data(db, ticket) for ticket in db.scalars(query)]

    @app.get("/api/tickets/{ticket_id}")
    def ticket(ticket_id: str, _actor=Depends(any_user)):
        with sessions() as db:
            row = db.get(MaintenanceTicket, ticket_id)
            if not row:
                raise HTTPException(404, "Maintenance ticket not found")
            return ticket_data(db, row)

    @app.post("/api/tickets/{ticket_id}/approve")
    def approve_ticket(ticket_id: str, actor=Depends(ticket_create)):
        with sessions.begin() as db:
            row = db.get(MaintenanceTicket, ticket_id)
            if not row:
                raise HTTPException(404, "Maintenance ticket not found")
            if row.data["status"] != "draft":
                raise HTTPException(409, "Only draft tickets can be approved")
            row.data = {
                **row.data,
                "status": "approved",
                "approved_at": clock().isoformat(),
                "approved_by": actor["username"],
            }
            audit(db, actor["id"], "ticket.approve", "maintenance_ticket", ticket_id)
            return ticket_data(db, row)

    def require_assigned(db, row, actor):
        if actor["role"] != "administrator" and row.assigned_user_id != actor["id"]:
            raise HTTPException(403, "Ticket is assigned to another technician")

    @app.post("/api/tickets/{ticket_id}/start")
    def start_ticket(ticket_id: str, actor=Depends(ticket_work)):
        with sessions.begin() as db:
            row = db.get(MaintenanceTicket, ticket_id)
            if not row:
                raise HTTPException(404, "Maintenance ticket not found")
            require_assigned(db, row, actor)
            if row.data["status"] != "approved":
                raise HTTPException(409, "Only approved tickets can be started")
            row.data = {
                **row.data,
                "status": "in_progress",
                "started_at": clock().isoformat(),
            }
            audit(db, actor["id"], "ticket.start", "maintenance_ticket", ticket_id)
            return ticket_data(db, row)

    @app.post("/api/tickets/{ticket_id}/resolve")
    def resolve_ticket(
        ticket_id: str, body: TicketResolution, actor=Depends(ticket_work)
    ):
        with sessions.begin() as db:
            row = db.get(MaintenanceTicket, ticket_id)
            if not row:
                raise HTTPException(404, "Maintenance ticket not found")
            require_assigned(db, row, actor)
            if row.data["status"] != "in_progress":
                raise HTTPException(409, "Only in-progress tickets can be resolved")
            linked_incident = db.get(Incident, row.incident_id)
            resolved_at = clock().isoformat()
            row.data = {
                **row.data,
                "status": "resolved",
                "resolved_at": resolved_at,
                "resolution": body.resolution,
            }
            linked_incident.data = {
                **linked_incident.data,
                "status": "resolved",
                "resolution": body.resolution,
            }
            audit(
                db,
                actor["id"],
                "ticket.resolve",
                "maintenance_ticket",
                ticket_id,
                {"incident_id": row.incident_id},
            )
            return ticket_data(db, row)

    def get_record(model, identifier):
        with sessions() as db:
            row = db.get(model, identifier)
            if not row:
                raise HTTPException(404, "Record not found")
            return row.data

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        with sessions() as db:
            db.execute(select(1))
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        with sessions() as db:
            robots_by_status = Counter(row.data["status"] for row in db.scalars(select(Robot)))
            missions_by_status = Counter(row.data["status"] for row in db.scalars(select(Mission)))
            incidents_by_status = Counter(row.data["status"] for row in db.scalars(select(Incident)))
        return Response(
            metrics_registry.render(
                robots_by_status, missions_by_status, incidents_by_status
            ),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

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
            query = query.where(Telemetry.robot_id == robot_id)
        if mission_id is not None:
            query = query.where(Telemetry.mission_id == mission_id)
        query = query.order_by(Telemetry.occurred_at.desc(), Telemetry.id).limit(limit).offset(offset)
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
                 source_incident_id: str | None = None,
                 limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        with sessions() as db:
            query = select(Mission)
            if robot_id is not None:
                query = query.where(Mission.robot_id == robot_id)
            if status is not None:
                query = query.where(Mission.data["status"].as_string() == status)
            if source_incident_id is not None:
                query = query.where(
                    Mission.source_incident_id == source_incident_id
                )
            query = query.order_by(Mission.created_at.desc(), Mission.id).limit(limit).offset(offset)
            return [m.data for m in db.scalars(query)]

    @app.post("/api/missions", status_code=201)
    def create_mission(body: MissionRequest, actor=Depends(mission_write)):
        with sessions.begin() as db:
            if not db.get(Robot, body.robot_id):
                raise HTTPException(404, "Robot not found")
            mid = str(uuid4())
            data = {"id": mid, **body.model_dump(), "status": "pending", "created_at": clock().isoformat(), "started_at": None, "ended_at": None, "execution_step": 0, "completed_waypoints": 0}
            db.add(Mission(id=mid, robot_id=body.robot_id, created_at=data["created_at"], source_incident_id=None, data=data))
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
            action = (
                "mission.replacement_approve"
                if m.data.get("source_incident_id")
                else "mission.approve"
            )
            audit(db, actor["id"], action, "mission", m.id, {"robot_id": r.id})
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
                received_at = timestamp.isoformat()
                db.add(Telemetry(id=body.event_id, robot_id=body.robot_id, mission_id=body.mission_id, occurred_at=payload["occurred_at"], received_at=received_at, data={**payload, "received_at": received_at}))
                fresh = not r.data["last_event_at"] or body.occurred_at > datetime.fromisoformat(r.data["last_event_at"])
                recent = timestamp - body.occurred_at <= timedelta(seconds=15)
                active = db.get(Mission, r.data["mission_id"]) if r.data["mission_id"] else None
                idle = body.mission_id is None and (not active or active.data["status"] != "running")
                if fresh and recent and (body.mission_id == r.data["mission_id"] or idle):
                    faults = []
                    if body.sensor_status == "failed":
                        faults.append("sensor_failure")
                    if body.navigation_status == "failed":
                        faults.append("navigation_failure")
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
                query = query.where(Incident.robot_id == robot_id)
            if mission_id is not None:
                query = query.where(Incident.mission_id == mission_id)
            query = query.order_by(Incident.detected_at.desc(), Incident.id).limit(limit).offset(offset)
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
                investigation_guides(db, incident_data["type"]),
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

    def report_response(content: str, filename: str):
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/incidents/{incident_id}/report.html")
    def download_incident_report(incident_id: str, actor=Depends(any_user)):
        with sessions.begin() as db:
            incident_row = db.get(Incident, incident_id)
            if not incident_row:
                raise HTTPException(404, "Incident not found")
            incident_data = incident_row.data
            mission_row = (
                db.get(Mission, incident_data["mission_id"])
                if incident_data.get("mission_id")
                else None
            )
            evidence = [db.get(Telemetry, event_id) for event_id in incident_data.get("event_ids", [])]
            events_data = [row.data for row in evidence if row]
            investigation = investigate_records(
                incident_data,
                mission_row.data if mission_row else None,
                events_data,
                investigation_guides(db, incident_data["type"]),
            )
            ticket_rows = db.scalars(
                select(MaintenanceTicket).where(
                    MaintenanceTicket.incident_id == incident_id
                )
            )
            tickets_data = [ticket_data(db, row) for row in ticket_rows]
            generated_at = clock().isoformat()
            content = incident_report(
                incident_data,
                mission_row.data if mission_row else None,
                events_data,
                investigation,
                tickets_data,
                generated_at,
                actor["username"],
            )
            audit(
                db,
                actor["id"],
                "report.generate",
                "incident",
                incident_id,
                {"format": "html"},
            )
            return report_response(content, f"atlas-incident-{incident_id}.html")

    @app.get("/api/missions/{mission_id}/report.html")
    def download_mission_report(mission_id: str, actor=Depends(any_user)):
        with sessions.begin() as db:
            mission_row = db.get(Mission, mission_id)
            if not mission_row:
                raise HTTPException(404, "Mission not found")
            events_data = [
                row.data
                for row in db.scalars(
                    select(Telemetry)
                    .where(Telemetry.mission_id == mission_id)
                    .order_by(
                        Telemetry.occurred_at.desc(),
                        Telemetry.id,
                    )
                )
            ]
            incident_rows = list(
                db.scalars(
                    select(Incident).where(
                        Incident.mission_id == mission_id
                    )
                )
            )
            incidents_data = [row.data for row in incident_rows]
            incident_ids = [row.id for row in incident_rows]
            ticket_rows = (
                list(
                    db.scalars(
                        select(MaintenanceTicket).where(
                            MaintenanceTicket.incident_id.in_(incident_ids)
                        )
                    )
                )
                if incident_ids
                else []
            )
            tickets_data = [ticket_data(db, row) for row in ticket_rows]
            generated_at = clock().isoformat()
            content = mission_report(
                mission_row.data,
                events_data,
                incidents_data,
                tickets_data,
                generated_at,
                actor["username"],
            )
            audit(
                db,
                actor["id"],
                "report.generate",
                "mission",
                mission_id,
                {"format": "html"},
            )
            return report_response(content, f"atlas-mission-{mission_id}.html")

    dashboard = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
    if dashboard.is_dir():
        app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")

    return app


app = create_app()
