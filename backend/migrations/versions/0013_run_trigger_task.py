"""a workflow run remembers the task that started it

A Trigger node can start a run when a task moves into a status; the nodes of that run work with that task.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(sa.Column("trigger_task_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_workflow_runs_trigger_task", "tasks", ["trigger_task_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_constraint("fk_workflow_runs_trigger_task", type_="foreignkey")
        batch.drop_column("trigger_task_id")
