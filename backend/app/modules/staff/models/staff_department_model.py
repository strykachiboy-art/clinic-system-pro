from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.staff_department_enums import StaffDepartmentStatus


def _utcnow():
    return datetime.now(timezone.utc).replace(
        tzinfo=None
    )


class StaffDepartment(db.Model):
    __tablename__ = "staff_departments"

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_staff_departments_staff_clinic",
        ),
        db.ForeignKeyConstraint(
            ["department_id", "clinic_id"],
            ["departments.id", "departments.clinic_id"],
            name="fk_staff_departments_department_clinic",
        ),
        db.CheckConstraint(
            "ended_at IS NULL OR assigned_at <= ended_at",
            name="ck_staff_departments_valid_period",
        ),
        db.CheckConstraint(
            "status != 'ENDED' OR ended_at IS NOT NULL",
            name="ck_staff_departments_ended_requires_end",
        ),
        db.CheckConstraint(
            "status = 'ACTIVE' OR is_primary = FALSE",
            name="ck_staff_departments_primary_active_only",
        ),
        db.Index(
            "ix_staff_departments_clinic_staff_status",
            "clinic_id",
            "staff_id",
            "status",
        ),
        db.Index(
            "ix_staff_departments_clinic_department_status",
            "clinic_id",
            "department_id",
            "status",
        ),
        db.Index(
            "uq_staff_departments_active_membership",
            "clinic_id",
            "staff_id",
            "department_id",
            unique=True,
            postgresql_where=db.text(
                "status = 'ACTIVE'"
            ),
            sqlite_where=db.text(
                "status = 'ACTIVE'"
            ),
        ),
        db.Index(
            "uq_staff_departments_active_primary",
            "clinic_id",
            "staff_id",
            unique=True,
            postgresql_where=db.text(
                "status = 'ACTIVE' AND is_primary = TRUE"
            ),
            sqlite_where=db.text(
                "status = 'ACTIVE' AND is_primary = TRUE"
            ),
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

    staff_id = db.Column(
        db.Integer,
        nullable=False,
        index=True,
    )

    department_id = db.Column(
        db.Integer,
        nullable=False,
        index=True,
    )

    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    status = db.Column(
        db.Enum(
            StaffDepartmentStatus,
            name="staffdepartmentstatus",
        ),
        nullable=False,
        default=StaffDepartmentStatus.ACTIVE,
        index=True,
    )

    assigned_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
    )

    ended_at = db.Column(
        db.DateTime,
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    staff = db.relationship(
        "Staff",
        back_populates="department_memberships",
        foreign_keys=[staff_id, clinic_id],
        overlaps="department,clinic",
    )

    department = db.relationship(
        "Department",
        back_populates="staff_memberships",
        foreign_keys=[department_id, clinic_id],
        overlaps="staff,clinic",
    )

    clinic = db.relationship(
        "Clinic",
        foreign_keys=[clinic_id],
        overlaps="staff,department",
    )

    def __repr__(self) -> str:
        return (
            f"<StaffDepartment staff={self.staff_id} "
            f"department={self.department_id} "
            f"status={self.status.value}>"
        )
