from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import AttachmentType


def _utcnow():
    return datetime.now(timezone.utc)


class MessageAttachment(db.Model):
    __tablename__ = "chat_message_attachments"

    __table_args__ = (
        db.CheckConstraint(
            "file_name IS NULL OR length(trim(file_name)) > 0",
            name="ck_chat_message_attachments_file_name_nonempty",
        ),
        db.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0",
            name="ck_chat_message_attachments_file_size_non_negative",
        ),
        db.UniqueConstraint(
            "message_id",
            "storage_key",
            name="uq_chat_message_attachments_message_storage",
        ),
        db.Index(
            "ix_chat_message_attachments_message_created",
            "message_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_attachments_clinic_created",
            "clinic_id",
            "created_at",
            "id",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    message_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attachment_type = db.Column(
        db.Enum(
            AttachmentType,
            name="chat_attachment_type_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    file_name = db.Column(
        db.String(255),
        nullable=True,
    )

    mime_type = db.Column(
        db.String(150),
        nullable=False,
    )

    file_size_bytes = db.Column(
        db.BigInteger,
        nullable=True,
    )

    storage_key = db.Column(
        db.String(500),
        nullable=False,
    )

    checksum = db.Column(
        db.String(128),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    message = db.relationship(
        "Message",
        back_populates="attachments",
    )

    def __repr__(self):
        return (
            f"<MessageAttachment "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"type={self.attachment_type.value}>"
        )