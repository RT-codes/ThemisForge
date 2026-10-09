"""a custom status has an icon and says what it is for

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("board_statuses") as batch:
        batch.add_column(sa.Column("icon", sa.String(40), nullable=False, server_default="box"))
        batch.add_column(sa.Column("description", sa.String(300), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("board_statuses") as batch:
        batch.drop_column("description")
        batch.drop_column("icon")
