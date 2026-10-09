"""a project keeps a history of what was done to it

First entry: a deleted task, with a copy of it so it can be looked at (or brought back) later.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("actor", sa.String(100), nullable=False, server_default=""),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_events_project_id", "project_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_events_project_id", table_name="project_events")
    op.drop_table("project_events")
