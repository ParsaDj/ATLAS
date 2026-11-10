"""Add audited technical-document retirement.

Revision ID: 20261109_0006
Revises: 20261007_0005
Create Date: 2026-11-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261109_0006"
down_revision: Union[str, Sequence[str], None] = "20261007_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("technical_documents") as batch:
        batch.add_column(sa.Column("retired_at", sa.String(), nullable=True))
        batch.add_column(sa.Column("retired_by", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_technical_documents_retired_by",
            "users",
            ["retired_by"],
            ["id"],
        )
        batch.create_index("ix_technical_documents_retired_at", ["retired_at"])


def downgrade() -> None:
    with op.batch_alter_table("technical_documents") as batch:
        batch.drop_index("ix_technical_documents_retired_at")
        batch.drop_constraint("fk_technical_documents_retired_by", type_="foreignkey")
        batch.drop_column("retired_by")
        batch.drop_column("retired_at")
