"""never reuse the ids of volumes, agents and tool servers

SQLite gives a new row the id of the newest row that was deleted. Workflow nodes (and run options) refer to folders and
agents by id, so a stale reference could end up pointing at a different folder or agent. AUTOINCREMENT stops that.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("volumes", "agents", "mcp_servers")


def upgrade() -> None:
    for (
        table
    ) in TABLES:  # SQLite changes a table by recreating it; the rows, indexes and constraints are copied over
        with op.batch_alter_table(table, recreate="always", table_kwargs={"sqlite_autoincrement": True}):
            pass


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, recreate="always"):
            pass
