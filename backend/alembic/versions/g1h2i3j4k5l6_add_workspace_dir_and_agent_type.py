"""add workspace_dir and agent_type to conversations

Revision ID: g1h2i3j4k5l6
Revises: a1f6c9d2b7e4
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "a1f6c9d2b7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出新列，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("conversations")}

    if "workspace_dir" not in columns:
        op.add_column(
            "conversations", sa.Column("workspace_dir", sa.Text(), nullable=True)
        )
    if "agent_type" not in columns:
        op.add_column(
            "conversations", sa.Column("agent_type", sa.String(length=50), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("conversations", "agent_type")
    op.drop_column("conversations", "workspace_dir")
