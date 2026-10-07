"""agents and tool servers live in files in the project's config folder

The files are the source of truth; the rows keep the identity (tasks and workflows point at the id) and a parsed copy.
`path` stays empty until the file has been written, which the app does the first time it looks at a project.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("agents", "mcp_servers"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("path", sa.String(300), nullable=False, server_default=""))
            batch.add_column(sa.Column("config_error", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("mcp_servers") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("last_test", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers") as batch:
        batch.drop_column("last_test")
        batch.drop_column("description")
    for table in ("agents", "mcp_servers"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("config_error")
            batch.drop_column("path")
