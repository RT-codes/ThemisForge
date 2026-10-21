"""control tokens belong to a user, and may reach all of the user's projects (no project)

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create(name: str, *, by_user: bool) -> None:
    """The table as it is after (by_user) or before this change. SQLite cannot add a NOT NULL foreign key to a table,
    so the table is made again and its rows copied."""
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        *([sa.Column("user_id", sa.Integer(), nullable=False)] if by_user else []),
        sa.Column("project_id", sa.Integer(), nullable=by_user),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("scope", sa.String(length=10), server_default="read", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]
    constraints = [
        *([sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE")] if by_user else []),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    ]
    op.create_table(name, *columns, *constraints)


def _swap(*, by_user: bool, copy: str) -> None:
    _create("control_tokens_new", by_user=by_user)
    op.execute(copy)
    op.drop_table("control_tokens")
    op.rename_table("control_tokens_new", "control_tokens")
    with op.batch_alter_table("control_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_control_tokens_project_id"), ["project_id"], unique=False)
        if by_user:
            batch_op.create_index(batch_op.f("ix_control_tokens_user_id"), ["user_id"], unique=False)


def upgrade() -> None:
    _swap(
        by_user=True,
        copy="""
        INSERT INTO control_tokens_new
            (id, user_id, project_id, name, scope, token_hash, token_encrypted, token_hint, last_used_at, created_at)
        SELECT t.id, p.owner_id, t.project_id, t.name, t.scope, t.token_hash, t.token_encrypted, t.token_hint,
               t.last_used_at, t.created_at
        FROM control_tokens t JOIN projects p ON p.id = t.project_id
        """,
    )


def downgrade() -> None:
    # a token for all projects has no project to go back to
    _swap(
        by_user=False,
        copy="""
        INSERT INTO control_tokens_new
            (id, project_id, name, scope, token_hash, token_encrypted, token_hint, last_used_at, created_at)
        SELECT id, project_id, name, scope, token_hash, token_encrypted, token_hint, last_used_at, created_at
        FROM control_tokens WHERE project_id IS NOT NULL
        """,
    )
