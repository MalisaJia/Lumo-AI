"""add computer use audit table

Revision ID: f8a3b5c7d9e1
Revises: h2i3j4k5l6m7
Create Date: 2026-10-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a3b5c7d9e1"
down_revision: Union[str, Sequence[str], None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the computer use audit table."""
    op.create_table(
        "computer_use_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("screenshot_hash", sa.String(length=16), nullable=True),
        sa.Column("confirmation_status", sa.String(length=20), nullable=False),
        sa.Column("result_summary", sa.String(length=500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_computer_use_audit_conversation_id",
        "computer_use_audit",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the computer use audit table."""
    op.drop_index(
        "ix_computer_use_audit_conversation_id",
        table_name="computer_use_audit",
    )
    op.drop_table("computer_use_audit")
