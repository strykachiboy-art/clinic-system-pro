from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums.reports_enums import ReportFormat, ReportType
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GeneratedReport(db.Model):
    """
    Metadata for a generated report.

    Clinic and generator are nullable for authorized system-wide reports.
    """

    __tablename__ = "generated_reports"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
        index=True,
    )

    generated_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=True,
        index=True,
    )

    report_type = db.Column(
        db.Enum(ReportType),
        nullable=False,
        index=True,
    )

    report_format = db.Column(
        db.Enum(ReportFormat),
        nullable=False,
        default=ReportFormat.PDF,
        index=True,
    )

    filters = db.Column(
        db.JSON,
        nullable=True,
    )

    file_url = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="generated_reports",
    )

    generated_by = db.relationship(
        "Staff",
        back_populates="generated_reports",
    )

    def __repr__(self) -> str:
        return (
            f"<GeneratedReport "
            f"id={self.id} "
            f"report_type={self.report_type.value!r} "
            f"report_format={self.report_format.value!r} "
            f"clinic_id={self.clinic_id} "
            f"generated_by_id={self.generated_by_id} "
            f"created_at={self.created_at!r}>"
        )