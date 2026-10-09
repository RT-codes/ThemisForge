"""a project and a workspace can have an icon, and a project says what it is for

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("purpose", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("icon", sa.String(40), nullable=False, server_default=""))
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("icon", sa.String(40), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("icon")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("icon")
        batch.drop_column("purpose")
