"""add users table and user_id columns (multi-tenant groundwork)

Revision ID: a1f6c9d2b7e4
Revises: e7b2d4a9c8f1
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f6c9d2b7e4'
down_revision: Union[str, Sequence[str], None] = 'e7b2d4a9c8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    应用启动时的 create_all 可能已建出新表/新列，这里做幂等防护。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) users 表
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("username", sa.String(length=100), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )

    # 2) providers/conversations/memories 加 user_id 列（存量行由 DEFAULT 回填 'local'）
    for table in ("providers", "conversations", "memories"):
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "user_id" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "user_id",
                    sa.String(length=32),
                    nullable=False,
                    server_default="local",
                ),
            )

    # 3) user_id 相关索引
    indexes = {
        table: {ix["name"] for ix in inspector.get_indexes(table)}
        for table in ("providers", "conversations", "memories")
    }
    if "ix_providers_user_id" not in indexes["providers"]:
        op.create_index("ix_providers_user_id", "providers", ["user_id"])
    if "ix_conversations_user_id" not in indexes["conversations"]:
        op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    if "ix_conversations_user_updated" not in indexes["conversations"]:
        op.create_index(
            "ix_conversations_user_updated", "conversations", ["user_id", "updated_at"]
        )
    if "ix_memories_user_id" not in indexes["memories"]:
        op.create_index("ix_memories_user_id", "memories", ["user_id"])
    if "ix_memories_user_type_created" not in indexes["memories"]:
        op.create_index(
            "ix_memories_user_type_created",
            "memories",
            ["user_id", "memory_type", "created_at"],
        )

    # 4) settings 表：加 user_id 并把主键改为复合 (user_id, key)
    #    SQLite 不支持直接改主键，用 batch_alter_table 重建表（存量行回填 'local'）
    settings_columns = {c["name"] for c in inspector.get_columns("settings")}
    if "user_id" not in settings_columns:
        with op.batch_alter_table(
            "settings", recreate="always"
        ) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "user_id",
                    sa.String(length=32),
                    nullable=False,
                    server_default="local",
                )
            )
            batch_op.create_primary_key("pk_settings", ["user_id", "key"])


def downgrade() -> None:
    """Downgrade schema."""
    # settings 回退：去掉 user_id，主键还原为单列 key
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.drop_column("user_id")
        batch_op.create_primary_key("pk_settings", ["key"])

    op.drop_index("ix_memories_user_type_created", table_name="memories")
    op.drop_index("ix_memories_user_id", table_name="memories")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_providers_user_id", table_name="providers")

    op.drop_column("memories", "user_id")
    op.drop_column("conversations", "user_id")
    op.drop_column("providers", "user_id")

    op.drop_table("users")
