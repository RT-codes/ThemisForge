"""webhooks: addresses that make tasks, and the messages they received

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title_template", sa.String(length=200), server_default="", nullable=False),
        sa.Column("description_template", sa.Text(), server_default="", nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("harness", sa.String(length=20), server_default="", nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("workflow_ids", sa.JSON(), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("review_on_success", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("webhooks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_webhooks_project_id"), ["project_id"], unique=False)

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("event", sa.String(length=60), nullable=False),
        sa.Column("delivery_key", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("webhook_deliveries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_webhook_deliveries_webhook_id"), ["webhook_id"], unique=False)


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
