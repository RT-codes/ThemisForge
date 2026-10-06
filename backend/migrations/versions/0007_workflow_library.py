"""workflow library: many workflows per project, tasks that play a workflow

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# lets batch mode drop the unnamed unique constraint that 0006 created on workflows.project_id
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    with op.batch_alter_table("workflows", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("uq_workflows_project_id", type_="unique")
        batch_op.add_column(
            sa.Column("name", sa.String(length=100), server_default="Workflow", nullable=False)
        )
        batch_op.add_column(sa.Column("description", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_workflows_project_id"), ["project_id"], unique=False)
    op.execute("UPDATE workflows SET created_at = updated_at")
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    # runs belong to a workflow: the one each project had until now
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(sa.Column("workflow_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parent_run_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE workflow_runs SET workflow_id = (SELECT id FROM workflows WHERE workflows.project_id = workflow_runs.project_id)"
    )
    op.execute(
        "DELETE FROM workflow_node_runs WHERE run_id IN (SELECT id FROM workflow_runs WHERE workflow_id IS NULL)"
    )
    op.execute("DELETE FROM workflow_runs WHERE workflow_id IS NULL")
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.alter_column("workflow_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_workflow_runs_workflow_id", "workflows", ["workflow_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            "fk_workflow_runs_parent_run_id", "workflow_runs", ["parent_run_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index(batch_op.f("ix_workflow_runs_workflow_id"), ["workflow_id"], unique=False)

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("workflow_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_workflow_id", "workflows", ["workflow_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(sa.Column("workflow_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_attempts_workflow_run_id", "workflow_runs", ["workflow_run_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_constraint("fk_attempts_workflow_run_id", type_="foreignkey")
        batch_op.drop_column("workflow_run_id")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_workflow_id", type_="foreignkey")
        batch_op.drop_column("workflow_id")
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflow_runs_workflow_id"))
        batch_op.drop_constraint("fk_workflow_runs_parent_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_workflow_runs_workflow_id", type_="foreignkey")
        batch_op.drop_column("parent_run_id")
        batch_op.drop_column("workflow_id")
    # one workflow per project again: keep the oldest of each
    op.execute("DELETE FROM workflows WHERE id NOT IN (SELECT MIN(id) FROM workflows GROUP BY project_id)")
    with op.batch_alter_table("workflows", naming_convention=NAMING) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflows_project_id"))
        batch_op.drop_column("created_at")
        batch_op.drop_column("description")
        batch_op.drop_column("name")
        batch_op.create_unique_constraint("uq_workflows_project_id", ["project_id"])
