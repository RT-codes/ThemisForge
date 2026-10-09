"""moving tasks between boards and spawning follow-ups

A task can remember the task it was spawned from, and the project history records where each event happened (workspace,
board and task) so it can be looked at per workspace, per board and per task. Those are plain numbers: history outlives
the things it names.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("origin_task_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_tasks_origin_task", "tasks", ["origin_task_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_tasks_origin_task_id", ["origin_task_id"])
    with op.batch_alter_table("project_events") as batch:
        for column in ("workspace_id", "board_id", "task_id"):
            batch.add_column(sa.Column(column, sa.Integer(), nullable=True))
            batch.create_index(f"ix_project_events_{column}", [column])


def downgrade() -> None:
    with op.batch_alter_table("project_events") as batch:
        for column in ("task_id", "board_id", "workspace_id"):
            batch.drop_index(f"ix_project_events_{column}")
            batch.drop_column(column)
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_origin_task_id")
        batch.drop_constraint("fk_tasks_origin_task", type_="foreignkey")
        batch.drop_column("origin_task_id")
