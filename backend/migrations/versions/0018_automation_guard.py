"""the automation guard: a limit on how often automation may move the same task

Workflows can now move and create tasks across boards, so a task could be sent back and forth for ever. A task counts how
many times automation handled it in a row (`hops`); the limit and the start cooldown can be set per project and per task.
A task made by a workflow step remembers which step (`origin_key`, unique), and the history says what set an event off.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("automation", sa.JSON(), nullable=True))
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("origin_key", sa.String(80), nullable=True))
        batch.add_column(sa.Column("hops", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("cooldown_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("max_hops", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_tasks_origin_key", ["origin_key"])
    with op.batch_alter_table("project_events") as batch:
        batch.add_column(sa.Column("cause", sa.String(80), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("project_events") as batch:
        batch.drop_column("cause")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("uq_tasks_origin_key", type_="unique")
        batch.drop_column("max_hops")
        batch.drop_column("cooldown_seconds")
        batch.drop_column("hops")
        batch.drop_column("origin_key")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("automation")
