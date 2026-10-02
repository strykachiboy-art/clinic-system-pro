"""add notifications

Revision ID: a17c9e4d6b52
Revises: 0e5862cc2239
Create Date: 2026-10-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a17c9e4d6b52"
down_revision = "0e5862cc2239"
branch_labels = None
depends_on = None


notification_type = postgresql.ENUM(
    "GENERAL",
    "APPOINTMENT",
    "CONSULTATION",
    "LAB",
    "PHARMACY",
    "PRESCRIPTION",
    "INVENTORY",
    "BILLING",
    "WARD",
    "AMBULANCE",
    "HIE",
    "SYSTEM",
    name="notificationtype",
    create_type=False,
)

notification_priority = postgresql.ENUM(
    "NORMAL",
    "HIGH",
    "URGENT",
    name="notificationpriority",
    create_type=False,
)

notification_channel = postgresql.ENUM(
    "IN_APP",
    "EMAIL",
    "SMS",
    "PUSH",
    name="notificationchannel",
    create_type=False,
)

notification_status = postgresql.ENUM(
    "PENDING",
    "SENT",
    "DELIVERED",
    "READ",
    "FAILED",
    name="notificationstatus",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()

    notification_type.create(bind, checkfirst=True)
    notification_priority.create(bind, checkfirst=True)
    notification_channel.create(bind, checkfirst=True)
    notification_status.create(bind, checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("notification_type", notification_type, nullable=False),
        sa.Column("priority", notification_priority, nullable=False),
        sa.Column("channel", notification_channel, nullable=False),
        sa.Column("status", notification_status, nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="notifications_clinic_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="notifications_user_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="notifications_pkey"),
    )

    op.create_index(
        "ix_notifications_channel",
        "notifications",
        ["channel"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_clinic_id",
        "notifications",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_delivered_at",
        "notifications",
        ["delivered_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_failed_at",
        "notifications",
        ["failed_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_is_read",
        "notifications",
        ["is_read"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_notification_type",
        "notifications",
        ["notification_type"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_priority",
        "notifications",
        ["priority"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_read_at",
        "notifications",
        ["read_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_reference_id",
        "notifications",
        ["reference_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_reference_type",
        "notifications",
        ["reference_type"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_sent_at",
        "notifications",
        ["sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_status",
        "notifications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_user_id",
        "notifications",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_sent_at", table_name="notifications")
    op.drop_index("ix_notifications_reference_type", table_name="notifications")
    op.drop_index("ix_notifications_reference_id", table_name="notifications")
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_priority", table_name="notifications")
    op.drop_index(
        "ix_notifications_notification_type",
        table_name="notifications",
    )
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_failed_at", table_name="notifications")
    op.drop_index(
        "ix_notifications_delivered_at",
        table_name="notifications",
    )
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_clinic_id", table_name="notifications")
    op.drop_index("ix_notifications_channel", table_name="notifications")

    op.drop_table("notifications")

    bind = op.get_bind()

    notification_status.drop(bind, checkfirst=True)
    notification_channel.drop(bind, checkfirst=True)
    notification_priority.drop(bind, checkfirst=True)
    notification_type.drop(bind, checkfirst=True)
