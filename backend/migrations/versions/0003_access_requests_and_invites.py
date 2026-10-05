"""access requests and invites

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_access_requests_email"), ["email"], unique=False)
        batch_op.create_index(batch_op.f("ix_access_requests_status"), ["status"], unique=False)

    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invites_email"), ["email"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invites_email"))

    op.drop_table("invites")
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_access_requests_status"))
        batch_op.drop_index(batch_op.f("ix_access_requests_email"))

    op.drop_table("access_requests")
