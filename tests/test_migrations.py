from pathlib import Path

from alembic import command
from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine, inspect, select
from sqlalchemy.orm import Session

from apps.api.main import Base, Incident, Mission, Robot, Telemetry
from apps.api.migrations import (
    alembic_config,
    require_current_schema,
    upgrade_database,
)


REVISION = "20261007_0005"
DOMAIN_TABLES = {
    "robots",
    "missions",
    "telemetry",
    "incidents",
    "users",
    "auth_sessions",
    "audit_logs",
    "maintenance_tickets",
    "technical_documents",
}


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def test_initial_migration_creates_versioned_schema_and_matches_models(tmp_path):
    url = sqlite_url(tmp_path / "fresh.db")
    upgrade_database(url)
    engine = create_engine(url)

    assert set(inspect(engine).get_table_names()) == DOMAIN_TABLES | {
        "alembic_version"
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == REVISION

    command.check(alembic_config(url))
    require_current_schema(engine)
    engine.dispose()


def test_application_rejects_an_unmigrated_database(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "unmigrated.db"))
    try:
        require_current_schema(engine)
    except RuntimeError as error:
        assert "alembic upgrade head" in str(error)
    else:
        raise AssertionError("unmigrated database was accepted")
    finally:
        engine.dispose()


def test_initial_migration_can_downgrade_and_reapply(tmp_path):
    url = sqlite_url(tmp_path / "roundtrip.db")
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    assert DOMAIN_TABLES.isdisjoint(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    assert DOMAIN_TABLES.issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_initial_migration_adopts_legacy_schema_without_data_loss(tmp_path):
    url = sqlite_url(tmp_path / "legacy.db")
    engine = create_engine(url)
    legacy = MetaData()
    Table("robots", legacy, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
    Table("missions", legacy, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
    Table("telemetry", legacy, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
    Table("incidents", legacy, Column("id", String, primary_key=True), Column("dedup_key", String, unique=True, nullable=False), Column("data", JSON, nullable=False))
    legacy.create_all(engine)
    robot_data = {
        "id": "robot-existing",
        "name": "Existing robot",
        "status": "unknown",
    }
    with Session(engine) as session, session.begin():
        session.execute(legacy.tables["robots"].insert().values(id="robot-existing", data=robot_data))
    engine.dispose()

    upgrade_database(url)

    engine = create_engine(url)
    with Session(engine) as session:
        assert session.scalar(select(Robot).where(Robot.id == "robot-existing")).data == robot_data
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == REVISION
    engine.dispose()


def test_operational_index_migration_backfills_records_and_constraints(tmp_path):
    url = sqlite_url(tmp_path / "backfill.db")
    config = alembic_config(url)
    command.upgrade(config, "20261003_0004")
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(engine)
    robot = {"id": "robot-1", "name": "Robot 1"}
    mission = {"id": "mission-1", "robot_id": "robot-1", "created_at": "2026-10-07T10:00:00+00:00", "source_incident_id": None}
    event = {"event_id": "event-1", "robot_id": "robot-1", "mission_id": "mission-1", "occurred_at": "2026-10-07T10:01:00+00:00", "received_at": "2026-10-07T10:01:01+00:00"}
    incident = {"id": "incident-1", "robot_id": "robot-1", "mission_id": "mission-1", "type": "low_battery", "detected_at": "2026-10-07T10:01:01+00:00"}
    with engine.begin() as connection:
        connection.execute(metadata.tables["robots"].insert().values(id=robot["id"], data=robot))
        connection.execute(metadata.tables["missions"].insert().values(id=mission["id"], data=mission))
        connection.execute(metadata.tables["telemetry"].insert().values(id=event["event_id"], data=event))
        connection.execute(metadata.tables["incidents"].insert().values(id=incident["id"], dedup_key="mission-1:low_battery", data=incident))
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert {item["name"] for item in inspector.get_foreign_keys("telemetry")} == {
        "fk_telemetry_robot_id",
        "fk_telemetry_mission_id",
    }
    assert "ix_telemetry_mission_occurred" in {
        item["name"] for item in inspector.get_indexes("telemetry")
    }
    with Session(engine) as session:
        stored_mission = session.get(Mission, "mission-1")
        stored_event = session.get(Telemetry, "event-1")
        stored_incident = session.get(Incident, "incident-1")
        assert (stored_mission.robot_id, stored_mission.created_at) == (
            mission["robot_id"], mission["created_at"]
        )
        assert (stored_event.mission_id, stored_event.occurred_at, stored_event.received_at) == (
            event["mission_id"], event["occurred_at"], event["received_at"]
        )
        assert (stored_incident.fault_type, stored_incident.detected_at) == (
            incident["type"], incident["detected_at"]
        )
    engine.dispose()

    command.downgrade(config, "20261003_0004")
    engine = create_engine(url)
    assert "robot_id" not in {
        column["name"] for column in inspect(engine).get_columns("missions")
    }
    with engine.connect() as connection:
        assert connection.execute(
            select(Table("missions", MetaData(), autoload_with=engine).c.data)
        ).scalar_one() == mission
    engine.dispose()
