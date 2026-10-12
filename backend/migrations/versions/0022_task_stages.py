"""a task plays an ordered list of workflows (stages) instead of a single one

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_stages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "workflow_run_id",
            sa.Integer(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_task_stages_task_id", "task_stages", ["task_id"])
    op.create_index("ix_task_stages_workflow_id", "task_stages", ["workflow_id"])
    # a task that played one workflow now has it as its single stage
    op.execute(
        "INSERT INTO task_stages (task_id, position, workflow_id) "
        "SELECT id, 0, workflow_id FROM tasks WHERE workflow_id IS NOT NULL"
    )
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_workflow_id", type_="foreignkey")  # named in 0007
        batch.drop_column("workflow_id")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(
            sa.Column(
                "workflow_id",
                sa.Integer(),
                sa.ForeignKey("workflows.id", ondelete="SET NULL", name="fk_tasks_workflow_id"),
                nullable=True,
            )
        )
    # only the first stage fits in a single column
    op.execute(
        "UPDATE tasks SET workflow_id = ("
        "SELECT workflow_id FROM task_stages WHERE task_id = tasks.id ORDER BY position LIMIT 1)"
    )
    op.drop_table("task_stages")
