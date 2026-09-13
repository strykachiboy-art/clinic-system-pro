"""remove legacy messages table

Revision ID: 3136bdf41623
Revises: 5d4291882625
Create Date: 2026-09-13 12:16:12.556768

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3136bdf41623'
down_revision = '5d4291882625'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("messages")

    # Remove PostgreSQL enum types belonging exclusively to the
    # deleted legacy messages table.
    op.execute("DROP TYPE IF EXISTS messagetype")
    op.execute("DROP TYPE IF EXISTS messagestatus")
    op.execute("DROP TYPE IF EXISTS messagepriority")


def downgrade():
    message_type = sa.Enum(
        "DIRECT",
        "SYSTEM",
        "CLINICAL",
        "APPOINTMENT",
        "LAB",
        "PHARMACY",
        "BILLING",
        "GENERAL",
        name="messagetype",
    )

    message_status = sa.Enum(
        "DRAFT",
        "SENT",
        "ARCHIVED",
        name="messagestatus",
    )

    message_priority = sa.Enum(
        "NORMAL",
        "HIGH",
        "URGENT",
        name="messagepriority",
    )

    message_type.create(op.get_bind(), checkfirst=True)
    message_status.create(op.get_bind(), checkfirst=True)
    message_priority.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("message_type", message_type, nullable=False),
        sa.Column("status", message_status, nullable=False),
        sa.Column("priority", message_priority, nullable=False),
        sa.Column("parent_message_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="messages_clinic_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["parent_message_id"],
            ["messages.id"],
            name="messages_parent_message_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name="messages_recipient_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name="messages_sender_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
