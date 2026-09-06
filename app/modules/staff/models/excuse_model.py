from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Excuse(db.Model):
    __tablename__ = "excuses"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    leave_request_id = db.Column(
        db.Integer,
        db.ForeignKey("leave_requests.id"),
        nullable=True,
        index=True,
    )

    excuse_type = db.Column(
        db.Enum(ExcuseType),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(ExcuseStatus),
        default=ExcuseStatus.PENDING,
        nullable=False,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    document_url = db.Column(
        db.String(500),
        nullable=True,
    )

    reviewed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    staff = db.relationship(
        "Staff",
        back_populates="excuses",
        foreign_keys=[staff_id],
    )

    leave_request = db.relationship(
        "LeaveRequest",
        back_populates="excuses",
        foreign_keys=[leave_request_id],
    )

    reviewed_by_user = db.relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
    )
    
    rejection_reason = db.Column(
       db.String(2000),
       nullable=True
    
   )

    def __repr__(self):
        return (
            f"<Excuse Staff {self.staff_id} "
            f"({self.excuse_type.value} - {self.status.value})>"
        )