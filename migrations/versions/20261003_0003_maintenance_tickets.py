"""Add maintenance ticket workflow records.

Revision ID: 20261003_0003
Revises: 20260928_0002
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261003_0003"
down_revision: Union[str, Sequence[str], None] = "20260928_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maintenance_tickets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("assigned_user_id", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_maintenance_tickets_assigned_user_id"),
        "maintenance_tickets",
        ["assigned_user_id"],
    )
    op.create_index(
        op.f("ix_maintenance_tickets_incident_id"),
        "maintenance_tickets",
        ["incident_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_maintenance_tickets_incident_id"),
        table_name="maintenance_tickets",
    )
    op.drop_index(
        op.f("ix_maintenance_tickets_assigned_user_id"),
        table_name="maintenance_tickets",
    )
    op.drop_table("maintenance_tickets")
