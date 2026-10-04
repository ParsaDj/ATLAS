"""Add immutable versioned technical documents.

Revision ID: 20261003_0004
Revises: 20261003_0003
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261003_0004"
down_revision: Union[str, Sequence[str], None] = "20261003_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "technical_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("fault", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.create_index(op.f("ix_technical_documents_fault"), "technical_documents", ["fault"])
    op.create_index(op.f("ix_technical_documents_approved"), "technical_documents", ["approved"])
    op.create_index(op.f("ix_technical_documents_created_at"), "technical_documents", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_technical_documents_created_at"), table_name="technical_documents")
    op.drop_index(op.f("ix_technical_documents_approved"), table_name="technical_documents")
    op.drop_index(op.f("ix_technical_documents_fault"), table_name="technical_documents")
    op.drop_table("technical_documents")
