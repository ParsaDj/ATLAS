from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from apps.api.main import Base, Incident, Mission, Robot, Telemetry
from apps.api.migrations import (
    alembic_config,
    require_current_schema,
    upgrade_database,
)


REVISION = "20260928_0002"
DOMAIN_TABLES = {
    "robots",
    "missions",
    "telemetry",
    "incidents",
    "users",
    "auth_sessions",
    "audit_logs",
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
    Base.metadata.create_all(
        engine,
        tables=[
            Robot.__table__,
            Mission.__table__,
            Telemetry.__table__,
            Incident.__table__,
        ],
    )
    robot_data = {
        "id": "robot-existing",
        "name": "Existing robot",
        "status": "unknown",
    }
    with Session(engine) as session, session.begin():
        session.add(Robot(id="robot-existing", data=robot_data))
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
