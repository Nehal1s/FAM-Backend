"""user auth_method, display_name, idempotency_key

Revision ID: 002
Revises: 001
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_method",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("users", sa.Column("display_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index("ix_users_idempotency_key", "users", ["idempotency_key"], unique=True)
    op.alter_column("users", "auth_method", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_idempotency_key", table_name="users")
    op.drop_column("users", "idempotency_key")
    op.drop_column("users", "display_name")
    op.drop_column("users", "auth_method")
