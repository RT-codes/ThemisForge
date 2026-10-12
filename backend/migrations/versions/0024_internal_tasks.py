"""tasks made by a workflow's Agent node are internal: kept off the boards and out of the counts

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("internal", sa.Boolean(), nullable=False, server_default="0"))
    # what Agent nodes made before this existed: they were already told apart by the node run that points at them
    op.execute(
        "UPDATE tasks SET internal = 1 WHERE id IN "
        "(SELECT task_id FROM workflow_node_runs WHERE kind = 'agent' AND task_id IS NOT NULL)"
    )


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("internal")
