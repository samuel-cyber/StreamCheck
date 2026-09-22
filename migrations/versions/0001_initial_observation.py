"""Initial observation table

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("photo_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "text_description", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "ai_indicators", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column("ai_confidence", sa.Float(), nullable=False),
        sa.Column("ai_reasoning", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("fhir_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("reviewed_by", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observation_status_created", "observation", ["status", "created_at"])
    op.create_index("ix_observation_fhir_id", "observation", ["fhir_id"])


def downgrade() -> None:
    op.drop_index("ix_observation_fhir_id", table_name="observation")
    op.drop_index("ix_observation_status_created", table_name="observation")
    op.drop_table("observation")
