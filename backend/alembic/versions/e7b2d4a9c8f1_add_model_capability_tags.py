"""add model capability_tags

Revision ID: e7b2d4a9c8f1
Revises: d5a8c3f1e6b2
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b2d4a9c8f1'
down_revision: Union[str, Sequence[str], None] = 'd5a8c3f1e6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出带该列的新库，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("models")}
    if "capability_tags" in columns:
        return
    op.add_column("models", sa.Column("capability_tags", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("models", "capability_tags")
