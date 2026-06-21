"""repair missing trading212 columns for databases already stamped 062

Revision ID: 063
Revises: 062
Create Date: 2026-06-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "063"
down_revision: Union[str, None] = "062_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """Idempotently add columns introduced by revision 062.

    Some local/dev databases were stamped as 062 while the new columns were not
    actually present, causing runtime errors such as
    "column bank_connections.kind does not exist" when adding Trading 212.
    Keep this migration defensive so fresh databases where 062 did run remain
    unaffected, while already-stamped databases are repaired on upgrade.
    """
    if not _has_column("bank_connections", "kind"):
        op.add_column(
            "bank_connections",
            sa.Column("kind", sa.String(length=50), nullable=False, server_default="banking"),
        )
        op.alter_column("bank_connections", "kind", server_default=None)

    if not _has_column("accounts", "external_metadata"):
        op.add_column("accounts", sa.Column("external_metadata", sa.JSON(), nullable=True))

    if not _has_column("asset_transactions", "raw_data"):
        op.add_column("asset_transactions", sa.Column("raw_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    # No-op: revision 062 owns these columns. This repair migration only ensures
    # they exist when a database was incorrectly stamped 062 without them.
    pass
