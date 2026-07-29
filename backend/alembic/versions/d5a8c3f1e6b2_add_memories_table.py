"""add memories table

Revision ID: d5a8c3f1e6b2
Revises: c9f4a2d7e1b3
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a8c3f1e6b2'
down_revision: Union[str, Sequence[str], None] = 'c9f4a2d7e1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出新表，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("memories"):
        return
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("memory_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("source_conversation_id", sa.String(length=32), nullable=True),
        sa.Column("source_message_id", sa.String(length=32), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memories_type_created", "memories", ["memory_type", "created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memories_type_created", table_name="memories")
    op.drop_table("memories")
