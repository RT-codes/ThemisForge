"""attempt usage: which harness and model an attempt ran on, and the tokens it spent

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("harness", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("billing", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reasoning_output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.drop_column("reasoning_output_tokens")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("cached_input_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("billing")
        batch_op.drop_column("model")
        batch_op.drop_column("harness")
