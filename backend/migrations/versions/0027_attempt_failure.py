"""why a failed attempt failed

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attempts") as batch:
        batch.add_column(sa.Column("failure", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch:
        batch.drop_column("failure")
