"""add message sources column and settings table

Revision ID: b3e7a1c4d2f9
Revises: 8cb50fedb7af
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e7a1c4d2f9'
down_revision: Union[str, Sequence[str], None] = '8cb50fedb7af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出 settings 表/新列，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("messages")}
    if "sources" not in columns:
        op.add_column("messages", sa.Column("sources", sa.Text(), nullable=True))

    if "settings" not in inspector.get_table_names():
        op.create_table(
            "settings",
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("settings")
    op.drop_column("messages", "sources")
