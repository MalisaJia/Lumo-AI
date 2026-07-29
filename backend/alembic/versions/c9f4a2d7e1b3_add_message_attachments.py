"""add message attachments column

Revision ID: c9f4a2d7e1b3
Revises: b3e7a1c4d2f9
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f4a2d7e1b3'
down_revision: Union[str, Sequence[str], None] = 'b3e7a1c4d2f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出新列，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("messages")}
    if "attachments" not in columns:
        op.add_column("messages", sa.Column("attachments", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("messages", "attachments")
