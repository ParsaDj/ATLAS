"""Index immutable operational record fields.

Revision ID: 20261007_0005
Revises: 20261003_0004
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261007_0005"
down_revision: Union[str, Sequence[str], None] = "20261003_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(table_name: str, fields: dict[str, str]) -> None:
    table = sa.table(
        table_name,
        sa.column("id", sa.String()),
        sa.column("data", sa.JSON()),
        *(sa.column(field, sa.String()) for field in fields),
    )
    connection = op.get_bind()
    for identifier, data in connection.execute(sa.select(table.c.id, table.c.data)):
        values = {column: data.get(json_key) for column, json_key in fields.items()}
        connection.execute(
            table.update().where(table.c.id == identifier).values(**values)
        )


def upgrade() -> None:
    with op.batch_alter_table("missions") as batch:
        batch.add_column(sa.Column("robot_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.String(), nullable=True))
        batch.add_column(sa.Column("source_incident_id", sa.String(), nullable=True))
    with op.batch_alter_table("telemetry") as batch:
        batch.add_column(sa.Column("robot_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("mission_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("occurred_at", sa.String(), nullable=True))
        batch.add_column(sa.Column("received_at", sa.String(), nullable=True))
    with op.batch_alter_table("incidents") as batch:
        batch.add_column(sa.Column("robot_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("mission_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("fault_type", sa.String(), nullable=True))
        batch.add_column(sa.Column("detected_at", sa.String(), nullable=True))

    _backfill("missions", {"robot_id": "robot_id", "created_at": "created_at", "source_incident_id": "source_incident_id"})
    _backfill("telemetry", {"robot_id": "robot_id", "mission_id": "mission_id", "occurred_at": "occurred_at", "received_at": "received_at"})
    _backfill("incidents", {"robot_id": "robot_id", "mission_id": "mission_id", "fault_type": "type", "detected_at": "detected_at"})

    with op.batch_alter_table("missions") as batch:
        batch.alter_column("robot_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("created_at", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_missions_robot_id", "robots", ["robot_id"], ["id"])
        batch.create_index("ix_missions_robot_id", ["robot_id"])
        batch.create_index("ix_missions_created_at", ["created_at"])
        batch.create_index("ix_missions_source_incident_id", ["source_incident_id"])
        batch.create_index("ix_missions_robot_created", ["robot_id", "created_at"])
    with op.batch_alter_table("telemetry") as batch:
        batch.alter_column("robot_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("occurred_at", existing_type=sa.String(), nullable=False)
        batch.alter_column("received_at", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_telemetry_robot_id", "robots", ["robot_id"], ["id"])
        batch.create_foreign_key("fk_telemetry_mission_id", "missions", ["mission_id"], ["id"])
        batch.create_index("ix_telemetry_robot_id", ["robot_id"])
        batch.create_index("ix_telemetry_mission_id", ["mission_id"])
        batch.create_index("ix_telemetry_occurred_at", ["occurred_at"])
        batch.create_index("ix_telemetry_received_at", ["received_at"])
        batch.create_index("ix_telemetry_robot_occurred", ["robot_id", "occurred_at"])
        batch.create_index("ix_telemetry_mission_occurred", ["mission_id", "occurred_at"])
    with op.batch_alter_table("incidents") as batch:
        batch.alter_column("robot_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("fault_type", existing_type=sa.String(), nullable=False)
        batch.alter_column("detected_at", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_incidents_robot_id", "robots", ["robot_id"], ["id"])
        batch.create_foreign_key("fk_incidents_mission_id", "missions", ["mission_id"], ["id"])
        batch.create_index("ix_incidents_robot_id", ["robot_id"])
        batch.create_index("ix_incidents_mission_id", ["mission_id"])
        batch.create_index("ix_incidents_fault_type", ["fault_type"])
        batch.create_index("ix_incidents_detected_at", ["detected_at"])
        batch.create_index("ix_incidents_robot_detected", ["robot_id", "detected_at"])
        batch.create_index("ix_incidents_mission_detected", ["mission_id", "detected_at"])


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch:
        batch.drop_index("ix_incidents_mission_detected")
        batch.drop_index("ix_incidents_robot_detected")
        batch.drop_index("ix_incidents_detected_at")
        batch.drop_index("ix_incidents_fault_type")
        batch.drop_index("ix_incidents_mission_id")
        batch.drop_index("ix_incidents_robot_id")
        batch.drop_constraint("fk_incidents_mission_id", type_="foreignkey")
        batch.drop_constraint("fk_incidents_robot_id", type_="foreignkey")
        batch.drop_column("detected_at")
        batch.drop_column("fault_type")
        batch.drop_column("mission_id")
        batch.drop_column("robot_id")
    with op.batch_alter_table("telemetry") as batch:
        batch.drop_index("ix_telemetry_mission_occurred")
        batch.drop_index("ix_telemetry_robot_occurred")
        batch.drop_index("ix_telemetry_received_at")
        batch.drop_index("ix_telemetry_occurred_at")
        batch.drop_index("ix_telemetry_mission_id")
        batch.drop_index("ix_telemetry_robot_id")
        batch.drop_constraint("fk_telemetry_mission_id", type_="foreignkey")
        batch.drop_constraint("fk_telemetry_robot_id", type_="foreignkey")
        batch.drop_column("received_at")
        batch.drop_column("occurred_at")
        batch.drop_column("mission_id")
        batch.drop_column("robot_id")
    with op.batch_alter_table("missions") as batch:
        batch.drop_index("ix_missions_robot_created")
        batch.drop_index("ix_missions_source_incident_id")
        batch.drop_index("ix_missions_created_at")
        batch.drop_index("ix_missions_robot_id")
        batch.drop_constraint("fk_missions_robot_id", type_="foreignkey")
        batch.drop_column("source_incident_id")
        batch.drop_column("created_at")
        batch.drop_column("robot_id")
