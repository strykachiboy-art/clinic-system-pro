from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.department_enums import DepartmentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(db.Model):
    __tablename__ = "departments"

    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id",
            "code",
            name="uq_departments_clinic_code",
        ),
        db.UniqueConstraint(
            "clinic_id",
            "name",
            name="uq_departments_clinic_name",
        ),
        db.Index(
            "ix_departments_clinic_status_name",
            "clinic_id",
            "status",
            "name",
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

    code = db.Column(
        db.String(100),
        nullable=False,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    status = db.Column(
        db.Enum(DepartmentStatus),
        default=DepartmentStatus.ACTIVE,
        nullable=False,
        index=True,
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

    clinic = db.relationship(
        "Clinic",
        back_populates="departments",
    )

    def __repr__(self) -> str:
        return (
            f"<Department {self.name} "
            f"({self.code})>"
        )
