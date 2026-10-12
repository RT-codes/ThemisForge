"""a project or a board can be halted: nothing in it starts until it is resumed

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("boards") as batch:
        batch.add_column(sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("boards") as batch:
        batch.drop_column("halted_at")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("halted_at")
