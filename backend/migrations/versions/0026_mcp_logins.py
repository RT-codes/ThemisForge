"""sign ins to tool servers that ask for one, and the tools that say they need it

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_logins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(2000), nullable=False),
        sa.Column("scheme", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("credential_encrypted", sa.Text(), nullable=False),
        sa.Column("account", sa.String(320), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "resource", name="uq_mcp_logins_resource"),
    )
    op.create_index("ix_mcp_logins_user_id", "mcp_logins", ["user_id"])
    with op.batch_alter_table("mcp_servers") as batch:
        batch.add_column(sa.Column("auth", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers") as batch:
        batch.drop_column("auth")
    op.drop_table("mcp_logins")
