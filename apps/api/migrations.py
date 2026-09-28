"""Programmatic migration helpers used by tests and operational scripts."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["configured_url"] = True
    config.set_main_option("script_location", str(ROOT / "migrations"))
    rendered = make_url(database_url).render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    return config


def upgrade_database(database_url, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def require_current_schema(engine) -> None:
    config = alembic_config(engine.url)
    expected = set(ScriptDirectory.from_config(config).get_heads())
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    if current != expected:
        raise RuntimeError(
            "Database schema is not current: "
            f"expected {sorted(expected)}, found {sorted(current)}. "
            "Run 'alembic upgrade head' before starting ATLAS."
        )
