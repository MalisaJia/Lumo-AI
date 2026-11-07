"""add tasks and agent_runs tables

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_task_id",
            sa.String(32),
            sa.ForeignKey("tasks.id"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.String(32), nullable=True),
        sa.Column("blocks", sa.Text(), nullable=True),
        sa.Column("blocked_by", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_conversation_id", "tasks", ["conversation_id"])
    op.create_index("ix_tasks_status", "tasks", ["status", "conversation_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(32),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(32),
            sa.ForeignKey("tasks.id"),
            nullable=True,
        ),
        sa.Column(
            "parent_run_id",
            sa.String(32),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("tool_rounds", sa.Integer(), server_default="0"),
        sa.Column("token_usage", sa.Text(), nullable=True),
        sa.Column("workspace_dir", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_agent_runs_conversation_id",
        "agent_runs",
        ["conversation_id", "status"],
    )


def downgrade():
    op.drop_table("agent_runs")
    op.drop_table("tasks")
