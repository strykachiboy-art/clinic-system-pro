"""add critical operation idempotency records

Revision ID: c3e7a91d5b2f
Revises: 6b565bc6d8b8
Create Date: 2026-10-06 00:50:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c3e7a91d5b2f"
down_revision = "6b565bc6d8b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "idempotency_records",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "clinic_id",
            sa.Integer(),
            sa.ForeignKey("clinics.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "operation",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "request_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.String(length=80),
            nullable=True,
        ),
        sa.Column(
            "entity_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "clinic_id",
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_scope",
        ),
    )

    op.create_index(
        "ix_idempotency_records_clinic_id",
        "idempotency_records",
        ["clinic_id"],
        unique=False,
    )

    op.create_index(
        "ix_idempotency_records_user_id",
        "idempotency_records",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_idempotency_records_created_at",
        "idempotency_records",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_idempotency_records_clinic_operation_created",
        "idempotency_records",
        ["clinic_id", "operation", "created_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_idempotency_records_clinic_operation_created",
        table_name="idempotency_records",
    )

    op.drop_index(
        "ix_idempotency_records_created_at",
        table_name="idempotency_records",
    )

    op.drop_index(
        "ix_idempotency_records_user_id",
        table_name="idempotency_records",
    )

    op.drop_index(
        "ix_idempotency_records_clinic_id",
        table_name="idempotency_records",
    )

    op.drop_table("idempotency_records")
