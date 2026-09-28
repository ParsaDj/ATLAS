"""Create the initial ATLAS operational schema.

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28

The existence checks adopt databases created by ATLAS before Alembic was
introduced. Existing tables must have the expected columns; no data is copied
or deleted during adoption.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260928_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table_name: str) -> set[str] | None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return None
    return {column["name"] for column in inspector.get_columns(table_name)}


def _validate_legacy_table(table_name: str, expected: set[str]) -> bool:
    existing = _existing_columns(table_name)
    if existing is None:
        return False
    if existing != expected:
        raise RuntimeError(
            f"Cannot adopt legacy table {table_name!r}: expected columns "
            f"{sorted(expected)}, found {sorted(existing)}"
        )
    return True


def upgrade() -> None:
    if not _validate_legacy_table("robots", {"id", "data"}):
        op.create_table(
            "robots",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _validate_legacy_table("missions", {"id", "data"}):
        op.create_table(
            "missions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _validate_legacy_table("telemetry", {"id", "data"}):
        op.create_table(
            "telemetry",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _validate_legacy_table("incidents", {"id", "dedup_key", "data"}):
        op.create_table(
            "incidents",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("dedup_key", sa.String(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dedup_key"),
        )


def downgrade() -> None:
    op.drop_table("incidents")
    op.drop_table("telemetry")
    op.drop_table("missions")
    op.drop_table("robots")
