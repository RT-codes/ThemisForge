"""project cell profile, volumes, agents

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("cell_profile", sa.JSON(), nullable=True))

    op.create_table(
        "volumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("host_path", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=2), nullable=False),
        sa.Column("exclusive_write", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_volumes_project_id_name"),
    )
    op.create_index("ix_volumes_project_id", "volumes", ["project_id"])

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("harness", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=10), nullable=False),
        sa.Column("cell_profile", sa.JSON(), nullable=True),
        sa.Column("mounts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_agents_project_id_name"),
    )
    op.create_index("ix_agents_project_id", "agents", ["project_id"])

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("agent_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("run_options", sa.JSON(), nullable=True))
        batch_op.create_foreign_key("fk_tasks_agent_id", "agents", ["agent_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_agent_id", type_="foreignkey")
        batch_op.drop_column("run_options")
        batch_op.drop_column("agent_id")
    op.drop_index("ix_agents_project_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_volumes_project_id", table_name="volumes")
    op.drop_table("volumes")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("cell_profile")
