from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Conversation(db.Model):
    __tablename__ = "chat_conversations"

    __table_args__ = (
        db.CheckConstraint(
            "title IS NULL OR length(trim(title)) > 0",
            name="ck_chat_conversations_title_nonempty",
        ),
        db.CheckConstraint(
            "description IS NULL OR length(trim(description)) > 0",
            name="ck_chat_conversations_description_nonempty",
        ),
        db.Index(
            "ix_chat_conversations_clinic_status_updated",
            "clinic_id",
            "status",
            "updated_at",
            "id",
        ),
        db.Index(
            "ix_chat_conversations_clinic_type_status",
            "clinic_id",
            "conversation_type",
            "status",
            "id",
        ),
        db.Index(
            "ix_chat_conversations_clinic_patient",
            "clinic_id",
            "patient_id",
            "updated_at",
            "id",
        ),
        db.Index(
            "ix_chat_conversations_clinic_last_message",
            "clinic_id",
            "last_message_at",
            "id",
        ),
        db.Index(
            "ix_chat_conversations_created_by",
            "created_by_id",
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

    conversation_type = db.Column(
        db.Enum(ConversationType),
        nullable=False,
        default=ConversationType.DIRECT,
        index=True,
    )

    status = db.Column(
        db.Enum(ConversationStatus),
        nullable=False,
        default=ConversationStatus.ACTIVE,
        index=True,
    )

    title = db.Column(
        db.String(200),
        nullable=True,
    )

    description = db.Column(
        db.String(1000),
        nullable=True,
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    appointment_id = db.Column(
        db.Integer,
        db.ForeignKey("appointments.id"),
        nullable=True,
        index=True,
    )

    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultations.id"),
        nullable=True,
        index=True,
    )

    last_message_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    archived_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    closed_at = db.Column(
        db.DateTime(timezone=True),
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
        index=True,
    )

    clinic = db.relationship(
        "Clinic",
        foreign_keys=[clinic_id],
    )

    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_id],
    )

    patient = db.relationship(
        "Patient",
        foreign_keys=[patient_id],
    )

    appointment = db.relationship(
        "Appointment",
        foreign_keys=[appointment_id],
    )

    consultation = db.relationship(
        "Consultation",
        foreign_keys=[consultation_id],
    )

    def __repr__(self):
        return (
            f"<Conversation "
            f"id={self.id} "
            f"type={self.conversation_type.value} "
            f"status={self.status.value} "
            f"clinic_id={self.clinic_id}>"
        )