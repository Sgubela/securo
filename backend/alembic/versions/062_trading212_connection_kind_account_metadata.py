"""add trading212 connection kind and metadata columns

Revision ID: 062
Revises: 061
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bank_connections",
        sa.Column("kind", sa.String(length=50), nullable=False, server_default="banking"),
    )
    op.add_column("accounts", sa.Column("external_metadata", sa.JSON(), nullable=True))
    op.add_column("asset_transactions", sa.Column("raw_data", sa.JSON(), nullable=True))
    op.alter_column("bank_connections", "kind", server_default=None)


def downgrade() -> None:
    op.drop_column("asset_transactions", "raw_data")
    op.drop_column("accounts", "external_metadata")
    op.drop_column("bank_connections", "kind")
