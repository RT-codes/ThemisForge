"""custom statuses on a board

A board can add statuses of its own next to the seven built-in ones. Tasks refer to them as "custom:<id>".

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_statuses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_board_statuses_board_id", "board_statuses", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_board_statuses_board_id", table_name="board_statuses")
    op.drop_table("board_statuses")
