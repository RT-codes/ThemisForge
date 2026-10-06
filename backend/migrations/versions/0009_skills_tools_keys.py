"""agent skills, tool servers (MCP) and keys

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(sa.Column("skills", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("mcp_servers", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("secrets", sa.JSON(), server_default="[]", nullable=False))

    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("env", sa.JSON(), nullable=False),
        sa.Column("secret_env", sa.JSON(), nullable=False),
        sa.Column("bearer_secret_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_mcp_servers_project_id_name"),
    )
    op.create_index("ix_mcp_servers_project_id", "mcp_servers", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_project_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("secrets")
        batch_op.drop_column("mcp_servers")
        batch_op.drop_column("skills")
