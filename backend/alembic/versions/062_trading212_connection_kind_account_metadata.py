"""add trading212 connection kind and metadata columns

Revision ID: 062
Revises: 061
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "062_1"
down_revision: Union[str, None] = "062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Only add columns if they don't exist (the original "062" may have already
    # created them before the chain was renumbered to "062_1").
    for table, col, col_def in [
        ("bank_connections", "kind", sa.String(length=50), True, "banking"),
        ("accounts", "external_metadata", sa.JSON(), True, None),
        ("asset_transactions", "raw_data", sa.JSON(), True, None),
    ]:
        has_col = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :tbl AND column_name = :col"
            ),
            {"tbl": table, "col": col},
        ).scalar()
        if has_col is None:
            op.add_column(table, col_def(col, nullable=True))
        else:
            # Column exists — no-op.
            pass

    # Remove the default on "kind" if still present (idempotent).
    has_default = conn.execute(
        sa.text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'bank_connections' AND column_name = 'kind'"
        )
    ).scalar()
    if has_default is not None:
        op.alter_column("bank_connections", "kind", server_default=None)


def downgrade() -> None:
    op.drop_column("asset_transactions", "raw_data")
    op.drop_column("accounts", "external_metadata")
    op.drop_column("bank_connections", "kind")
