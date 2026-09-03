from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.reports_enums import ReportType, ReportFormat

def _utcnow():
    return datetime.now(timezone.utc)

class GeneratedReport(db.Model):
    """Log of exported/generated reports — the report data itself is computed live from
    existing models (Patient, Appointment, Invoice, etc.), this just tracks exports."""
    __tablename__ = "generated_reports"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True) 
    generated_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)

    report_type = db.Column(db.Enum(ReportType), nullable=False)
    report_format = db.Column(db.Enum(ReportFormat), default=ReportFormat.PDF, nullable=False)

    filters = db.Column(db.JSON, nullable=True)          
    file_url = db.Column(db.String(255), nullable=True)  

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    clinic = db.relationship("Clinic", back_populates="generated_reports")
    generated_by = db.relationship("Staff", back_populates="generated_reports")

    def __repr__(self):
        return f"<GeneratedReport {self.report_type.value} @ {self.created_at}>"