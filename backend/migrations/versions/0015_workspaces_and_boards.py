"""workspaces and boards

A project holds workspaces, a workspace holds boards, and every task lives on a board. Each existing project gets one
workspace ("Main") with one board ("Tasks") that all its tasks move onto, so nothing looks different afterwards.

Revision ID: 0015
Revises: 0014
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# the built-in statuses in board order (a copy on purpose: a migration must not change when the app does)
BUILTIN_COLUMNS = ["backlog", "ready", "running", "review", "done", "blocked", "failed"]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_workspaces_project_id", "workspaces", ["project_id"])
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_boards_project_id", "boards", ["project_id"])
    op.create_index("ix_boards_workspace_id", "boards", ["workspace_id"])

    with op.batch_alter_table("tasks") as batch:  # nullable until the tasks have a board
        batch.add_column(sa.Column("board_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    for (project_id,) in bind.execute(sa.text("SELECT id FROM projects")).fetchall():
        workspace_id = bind.execute(
            sa.text(
                "INSERT INTO workspaces (project_id, name, purpose, description, position, created_at) "
                "VALUES (:p, 'Main', '', '', 1.0, CURRENT_TIMESTAMP)"
            ),
            {"p": project_id},
        ).lastrowid
        board_id = bind.execute(
            sa.text(
                "INSERT INTO boards (project_id, workspace_id, name, purpose, position, columns, created_at) "
                "VALUES (:p, :w, 'Tasks', '', 1.0, :c, CURRENT_TIMESTAMP)"
            ),
            {"p": project_id, "w": workspace_id, "c": json.dumps(BUILTIN_COLUMNS)},
        ).lastrowid
        bind.execute(
            sa.text("UPDATE tasks SET board_id = :b WHERE project_id = :p"), {"b": board_id, "p": project_id}
        )

    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("board_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_tasks_board", "boards", ["board_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_tasks_board_id", ["board_id"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_board_id")
        batch.drop_constraint("fk_tasks_board", type_="foreignkey")
        batch.drop_column("board_id")
    op.drop_table("boards")
    op.drop_table("workspaces")
