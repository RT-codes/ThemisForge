"""connections to outside services, the project's choice of one, and which agents may use them

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("credential_encrypted", sa.Text(), nullable=False),
        sa.Column("account", sa.String(320), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "provider", "account", name="uq_connections_account"),
    )
    op.create_index("ix_connections_user_id", "connections", ["user_id"])
    op.create_table(
        "project_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column(
            "connection_id", sa.Integer(), sa.ForeignKey("connections.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "provider", name="uq_project_connections_provider"),
    )
    op.create_index("ix_project_connections_project_id", "project_connections", ["project_id"])
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("connections", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("connections")
    op.drop_table("project_connections")
    op.drop_table("connections")
