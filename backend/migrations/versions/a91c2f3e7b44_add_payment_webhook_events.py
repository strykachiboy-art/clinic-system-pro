"""add durable payment webhook event ledger

Revision ID: a91c2f3e7b44
Revises: c3e7a91d5b2f
Create Date: 2026-10-06 12:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a91c2f3e7b44"
down_revision = "c3e7a91d5b2f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_webhook_events",
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
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payments.id"),
            nullable=True,
        ),
        sa.Column(
            "gateway",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "reference",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "transaction_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "clinic_id",
            "gateway",
            "event_id",
            name="uq_payment_webhook_events_scope",
        ),
    )

    op.create_index(
        "ix_payment_webhook_events_clinic_id",
        "payment_webhook_events",
        ["clinic_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_webhook_events_gateway",
        "payment_webhook_events",
        ["gateway"],
        unique=False,
    )

    op.create_index(
        "ix_payment_webhook_events_payment_id",
        "payment_webhook_events",
        ["payment_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_webhook_events_created_at",
        "payment_webhook_events",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_payment_webhook_events_clinic_created",
        "payment_webhook_events",
        ["clinic_id", "created_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_payment_webhook_events_clinic_created",
        table_name="payment_webhook_events",
    )

    op.drop_index(
        "ix_payment_webhook_events_created_at",
        table_name="payment_webhook_events",
    )

    op.drop_index(
        "ix_payment_webhook_events_payment_id",
        table_name="payment_webhook_events",
    )

    op.drop_index(
        "ix_payment_webhook_events_gateway",
        table_name="payment_webhook_events",
    )

    op.drop_index(
        "ix_payment_webhook_events_clinic_id",
        table_name="payment_webhook_events",
    )

    op.drop_table("payment_webhook_events")
