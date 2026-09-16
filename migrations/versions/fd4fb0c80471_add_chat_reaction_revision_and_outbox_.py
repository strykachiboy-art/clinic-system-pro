"""Add chat reaction revision and outbox models

Revision ID: fd4fb0c80471
Revises: ef3b4d313dcb
Create Date: 2026-09-16 15:53:57.276956

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "fd4fb0c80471"
down_revision = "ef3b4d313dcb"
branch_labels = None
depends_on = None


CHAT_MESSAGE_TYPE_ENUM = postgresql.ENUM(
    "text",
    "image",
    "video",
    "audio",
    "file",
    "system",
    name="chat_message_type_enum",
)


def upgrade():
    # ------------------------------------------------------------------
    # PostgreSQL enum required by chat_messages.message_type.
    #
    # This must exist BEFORE the column is added.
    # ------------------------------------------------------------------
    CHAT_MESSAGE_TYPE_ENUM.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ------------------------------------------------------------------
    # Chat usage
    # ------------------------------------------------------------------
    op.create_table(
        "chat_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column(
            "direct_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "group_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "department_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "team_created",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.CheckConstraint(
            "department_created >= 0",
            name="ck_chat_usage_department_created_nonnegative",
        ),
        sa.CheckConstraint(
            "direct_created >= 0",
            name="ck_chat_usage_direct_created_nonnegative",
        ),
        sa.CheckConstraint(
            "group_created >= 0",
            name="ck_chat_usage_group_created_nonnegative",
        ),
        sa.CheckConstraint(
            "team_created >= 0",
            name="ck_chat_usage_team_created_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clinic_id",
            "user_id",
            "usage_date",
            name="uq_chat_usage_clinic_user_date",
        ),
    )

    with op.batch_alter_table(
        "chat_usage",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_chat_usage_clinic_date",
            ["clinic_id", "usage_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_usage_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_usage_usage_date"),
            ["usage_date"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_usage_user_date",
            ["user_id", "usage_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_usage_user_id"),
            ["user_id"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # Message reactions
    # ------------------------------------------------------------------
    op.create_table(
        "chat_message_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reaction", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "user_id",
            "reaction",
            name="uq_chat_message_reaction_user",
        ),
    )

    with op.batch_alter_table(
        "chat_message_reactions",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_chat_message_reactions_clinic_created",
            ["clinic_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_reactions_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_reactions_message_id"),
            ["message_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_message_reactions_message_reaction",
            ["message_id", "reaction"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_message_reactions_user_created",
            ["user_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_reactions_user_id"),
            ["user_id"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # Message revisions
    # ------------------------------------------------------------------
    op.create_table(
        "chat_message_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("edited_by_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("previous_content", sa.Text(), nullable=True),
        sa.Column(
            "previous_message_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["edited_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "revision_number",
            name="uq_chat_message_revision_number",
        ),
    )

    with op.batch_alter_table(
        "chat_message_revisions",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_chat_message_revisions_clinic_created",
            ["clinic_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_revisions_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_revisions_edited_by_id"),
            ["edited_by_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_message_revisions_editor_created",
            ["edited_by_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_message_revisions_message_created",
            ["message_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_message_revisions_message_id"),
            ["message_id"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # Chat outbox
    # ------------------------------------------------------------------
    op.create_table(
        "chat_outbox",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
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
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table(
        "chat_outbox",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_outbox_available_at"),
            ["available_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_outbox_clinic_created",
            ["clinic_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_outbox_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_outbox_message_created",
            ["message_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_outbox_message_id"),
            ["message_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_outbox_pending_available",
            ["status", "available_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_outbox_status"),
            ["status"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # Conversation avatar
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_conversations",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "avatar_storage_key",
                sa.String(length=500),
                nullable=True,
            )
        )

    # ------------------------------------------------------------------
    # Message type
    #
    # Existing rows need a value before the column can become NOT NULL.
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_messages",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "message_type",
                CHAT_MESSAGE_TYPE_ENUM,
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE chat_messages
        SET message_type = 'text'
        WHERE message_type IS NULL
        """
    )

    with op.batch_alter_table(
        "chat_messages",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "message_type",
            existing_type=CHAT_MESSAGE_TYPE_ENUM,
            nullable=False,
        )

        batch_op.create_index(
            "ix_chat_messages_conversation_status_created",
            ["conversation_id", "status", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_chat_messages_message_type"),
            ["message_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_chat_messages_sender_created",
            ["sender_id", "created_at"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # User profile image
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "users",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "profile_image_storage_key",
                sa.String(length=500),
                nullable=True,
            )
        )


def downgrade():
    # ------------------------------------------------------------------
    # User profile image
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "users",
        schema=None,
    ) as batch_op:
        batch_op.drop_column(
            "profile_image_storage_key",
        )

    # ------------------------------------------------------------------
    # Message type
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_messages",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_chat_messages_sender_created",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_messages_message_type"),
        )
        batch_op.drop_index(
            "ix_chat_messages_conversation_status_created",
        )
        batch_op.drop_column(
            "message_type",
        )

    # ------------------------------------------------------------------
    # Conversation avatar
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_conversations",
        schema=None,
    ) as batch_op:
        batch_op.drop_column(
            "avatar_storage_key",
        )

    # ------------------------------------------------------------------
    # Chat outbox
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_outbox",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_chat_outbox_status"),
        )
        batch_op.drop_index(
            "ix_chat_outbox_pending_available",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_outbox_message_id"),
        )
        batch_op.drop_index(
            "ix_chat_outbox_message_created",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_outbox_clinic_id"),
        )
        batch_op.drop_index(
            "ix_chat_outbox_clinic_created",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_outbox_available_at"),
        )

    op.drop_table("chat_outbox")

    # ------------------------------------------------------------------
    # Message revisions
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_message_revisions",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_chat_message_revisions_message_id"),
        )
        batch_op.drop_index(
            "ix_chat_message_revisions_message_created",
        )
        batch_op.drop_index(
            "ix_chat_message_revisions_editor_created",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_message_revisions_edited_by_id"),
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_message_revisions_clinic_id"),
        )
        batch_op.drop_index(
            "ix_chat_message_revisions_clinic_created",
        )

    op.drop_table("chat_message_revisions")

    # ------------------------------------------------------------------
    # Message reactions
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_message_reactions",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_chat_message_reactions_user_id"),
        )
        batch_op.drop_index(
            "ix_chat_message_reactions_user_created",
        )
        batch_op.drop_index(
            "ix_chat_message_reactions_message_reaction",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_message_reactions_message_id"),
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_message_reactions_clinic_id"),
        )
        batch_op.drop_index(
            "ix_chat_message_reactions_clinic_created",
        )

    op.drop_table("chat_message_reactions")

    # ------------------------------------------------------------------
    # Chat usage
    # ------------------------------------------------------------------
    with op.batch_alter_table(
        "chat_usage",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_chat_usage_user_id"),
        )
        batch_op.drop_index(
            "ix_chat_usage_user_date",
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_usage_usage_date"),
        )
        batch_op.drop_index(
            batch_op.f("ix_chat_usage_clinic_id"),
        )
        batch_op.drop_index(
            "ix_chat_usage_clinic_date",
        )

    op.drop_table("chat_usage")

    # ------------------------------------------------------------------
    # PostgreSQL enum
    #
    # Drop it only after chat_messages.message_type has been removed.
    # ------------------------------------------------------------------
    CHAT_MESSAGE_TYPE_ENUM.drop(
        op.get_bind(),
        checkfirst=True,
    )