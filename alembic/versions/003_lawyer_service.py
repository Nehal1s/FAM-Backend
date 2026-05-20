"""lawyer service tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lawyers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_type", sa.String(32), nullable=False, server_default="lawyer"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("bar_number", sa.String(64), nullable=False),
        sa.Column("license_jurisdiction", sa.String(128), nullable=False),
        sa.Column("firm_name", sa.String(255), nullable=True),
        sa.Column("specializations", sa.String(500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column(
            "promoted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("promoted_by", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lawyers_user_id", "lawyers", ["user_id"], unique=True)
    op.create_index("ix_lawyers_status", "lawyers", ["status"])

    op.create_table(
        "lawyer_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lawyer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lawyer_id"], ["lawyers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lawyer_contracts_lawyer_id", "lawyer_contracts", ["lawyer_id"])
    op.create_index("ix_lawyer_contracts_client_user_id", "lawyer_contracts", ["client_user_id"])
    op.create_index(
        "ix_lawyer_contracts_lawyer_client",
        "lawyer_contracts",
        ["lawyer_id", "client_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lawyer_contracts_lawyer_client", table_name="lawyer_contracts")
    op.drop_index("ix_lawyer_contracts_client_user_id", table_name="lawyer_contracts")
    op.drop_index("ix_lawyer_contracts_lawyer_id", table_name="lawyer_contracts")
    op.drop_table("lawyer_contracts")
    op.drop_index("ix_lawyers_status", table_name="lawyers")
    op.drop_index("ix_lawyers_user_id", table_name="lawyers")
    op.drop_table("lawyers")
