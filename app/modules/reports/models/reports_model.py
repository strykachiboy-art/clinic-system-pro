from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.reports_enums import ReportType, ReportFormat


def _utcnow():
    return datetime.now(timezone.utc)


class GeneratedReport(db.Model):
    """
    Log of generated/exported reports.

    The report contents are generated from the current application
    data by reports_service.

    This model stores:
    - which clinic the report belongs to
    - which staff member generated it
    - report type
    - output format
    - filters used
    - generated file location
    - timestamps
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
        default=ReportFormat.PDF,
        nullable=False,
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
        back_populates="generated_reports",
    )

    generated_by = db.relationship(
        "Staff",
        back_populates="generated_reports",
    )

    def __repr__(self):
        return (
            f"<GeneratedReport "
            f"{self.report_type.value} "
            f"@ {self.created_at}>"
        )