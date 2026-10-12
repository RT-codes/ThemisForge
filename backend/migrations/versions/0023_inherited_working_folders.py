"""attempts remember which working folder they used and what they changed in it

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attempts") as batch:
        batch.add_column(sa.Column("workdir_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("changes", sa.JSON(), nullable=True))
        batch.create_index("ix_attempts_workdir_id", ["workdir_id"])
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(sa.Column("workdir_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("workdir_id")
    with op.batch_alter_table("attempts") as batch:
        batch.drop_index("ix_attempts_workdir_id")
        batch.drop_column("changes")
        batch.drop_column("workdir_id")
