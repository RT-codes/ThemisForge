"""the Inbox status is now called Backlog

Tasks store the status by name, and so do the Task and Trigger nodes of a workflow (in the library and in the graph
copy kept with every run), so all three are renamed.

Revision ID: 0012
Revises: 0011
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_in_graphs(old: str, new: str) -> None:
    bind = op.get_bind()
    for table in ("workflows", "workflow_runs"):
        for row_id, graph in bind.execute(sa.text(f"SELECT id, graph FROM {table}")).fetchall():
            data = json.loads(graph) if isinstance(graph, str) else graph
            changed = False
            for node in (data or {}).get("nodes", []):
                config = node.get("config") or {}
                if config.get("status") == old:
                    config["status"] = new
                    changed = True
            if changed:
                bind.execute(
                    sa.text(f"UPDATE {table} SET graph = :g WHERE id = :i"),
                    {"g": json.dumps(data), "i": row_id},
                )


def upgrade() -> None:
    op.execute("UPDATE tasks SET status = 'backlog' WHERE status = 'inbox'")
    _rename_in_graphs("inbox", "backlog")


def downgrade() -> None:
    op.execute("UPDATE tasks SET status = 'inbox' WHERE status = 'backlog'")
    _rename_in_graphs("backlog", "inbox")
