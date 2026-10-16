"""approval gates: a workflow step that waits for a person, and the answer it was given

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_node_runs") as batch:
        batch.add_column(sa.Column("gate", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("decision", sa.String(length=10), server_default="", nullable=False))
        batch.add_column(sa.Column("decision_note", sa.Text(), server_default="", nullable=False))
        batch.add_column(sa.Column("decided_by", sa.String(length=100), server_default="", nullable=False))
        batch.create_index("ix_workflow_node_runs_status", ["status"])


def downgrade() -> None:
    with op.batch_alter_table("workflow_node_runs") as batch:
        batch.drop_index("ix_workflow_node_runs_status")
        batch.drop_column("decided_by")
        batch.drop_column("decision_note")
        batch.drop_column("decision")
        batch.drop_column("gate")
