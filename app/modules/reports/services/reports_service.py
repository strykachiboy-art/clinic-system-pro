import csv
import io
import os
from datetime import date, datetime, timezone
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.reports_enums import ReportType, ReportFormat
from app.modules.reports.models.reports_model import GeneratedReport

# Data sources — reused from modules whose services already exist.
# STAFF and INVENTORY are intentionally excluded: staff_service.py and
# inventory_service.py don't exist as usable code yet, so wiring
# real data-gathering for them now would mean guessing at their
# eventual query shape. Add them here once those services are built.
from app.modules.patient.services.patient_service import list_patients
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.billing.models.billing_model import Invoice
from app.modules.lab.models.lab_model import LabOrder
from app.modules.pharmacy.models.pharmacy_model import Drug, DrugBatch


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Data gatherers — or "extractors" — one per report type, all returning 
# the same (headers, rows) shape
# ---------------------------------------------------------------------

def _gather_patients(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    patients = list_patients(clinic_id=clinic_id, active_only=filters.get("active_only", True))
    headers = ["patient_number", "first_name", "last_name", "gender", "blood_type", "phone", "is_active"]
    rows = [
        [p.patient_number, p.first_name, p.last_name,
         p.gender.value if p.gender else None, p.blood_type.value, p.phone, p.is_active]
        for p in patients
    ]
    return headers, rows


def _gather_appointments(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    query = Appointment.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    if filters.get("date_from"):
        query = query.filter(Appointment.scheduled_start >= filters["date_from"])
    if filters.get("date_to"):
        query = query.filter(Appointment.scheduled_start <= filters["date_to"])

    appointments = query.order_by(Appointment.scheduled_start).all()
    headers = ["id", "patient_id", "staff_id", "scheduled_start", "scheduled_end", "status"]
    rows = [
        [a.id, a.patient_id, a.staff_id, a.scheduled_start.isoformat(),
         a.scheduled_end.isoformat(), a.status.value]
        for a in appointments
    ]
    return headers, rows


def _gather_billing(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    query = Invoice.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    if filters.get("date_from"):
        query = query.filter(Invoice.created_at >= filters["date_from"])
    if filters.get("date_to"):
        query = query.filter(Invoice.created_at <= filters["date_to"])

    invoices = query.order_by(Invoice.created_at).all()
    headers = ["invoice_number", "patient_id", "status", "total_amount", "amount_paid", "created_at"]
    rows = [
        [i.invoice_number, i.patient_id, i.status.value, str(i.total_amount), str(i.amount_paid), i.created_at.isoformat()]
        for i in invoices
    ]
    return headers, rows


def _gather_lab(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    query = LabOrder.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    if filters.get("date_from"):
        query = query.filter(LabOrder.created_at >= filters["date_from"])
    if filters.get("date_to"):
        query = query.filter(LabOrder.created_at <= filters["date_to"])

    orders = query.order_by(LabOrder.created_at).all()
    headers = ["id", "patient_id", "status", "created_at", "completed_at"]
    rows = [
        [o.id, o.patient_id, o.status.value, o.created_at.isoformat(),
         o.completed_at.isoformat() if o.completed_at else None]
        for o in orders
    ]
    return headers, rows


def _gather_pharmacy(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    query = Drug.query
    if clinic_id is not None:
        query = query.filter(db.or_(Drug.clinic_id == clinic_id, Drug.clinic_id.is_(None)))

    drugs = query.order_by(Drug.name).all()
    headers = ["drug_name", "category", "is_controlled", "total_usable_quantity", "total_expired_quantity"]
    rows = []
    for d in drugs:
        today = date.today()
        usable = sum(b.quantity_on_hand for b in d.batches if b.expiry_date >= today)
        expired = sum(b.quantity_on_hand for b in d.batches if b.expiry_date < today)
        rows.append([d.name, d.category.value, d.is_controlled, usable, expired])
    return headers, rows


def _gather_overview(clinic_id: int | None, filters: dict) -> tuple[list[str], list[list]]:
    """Cross-module summary — counts only, not full record dumps."""
    p_headers, p_rows = _gather_patients(clinic_id, filters)
    a_headers, a_rows = _gather_appointments(clinic_id, filters)
    b_headers, b_rows = _gather_billing(clinic_id, filters)
    l_headers, l_rows = _gather_lab(clinic_id, filters)

    headers = ["metric", "count"]
    rows = [
        ["total_patients", len(p_rows)],
        ["total_appointments", len(a_rows)],
        ["total_invoices", len(b_rows)],
        ["total_lab_orders", len(l_rows)],
    ]
    return headers, rows


_GATHERERS = {
    ReportType.OVERVIEW: _gather_overview,
    ReportType.PATIENTS: _gather_patients,
    ReportType.APPOINTMENTS: _gather_appointments,
    ReportType.BILLING: _gather_billing,
    ReportType.LAB: _gather_lab,
    ReportType.PHARMACY: _gather_pharmacy,
}

_UNSUPPORTED_TYPES = {ReportType.STAFF, ReportType.INVENTORY}


# ---------------------------------------------------------------------
# Export writers — one per format, all consuming the same (headers, rows) shape
# ---------------------------------------------------------------------

def _write_csv(headers: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _write_xlsx(headers: list[str], rows: list[list]) -> bytes:
    # Requires `openpyxl` — add to requirements.txt if not already present.
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _write_pdf(headers: list[str], rows: list[list]) -> bytes:
    raise NotImplementedError(
        "PDF export requires choosing a PDF library (e.g. reportlab, "
        "weasyprint) — not implemented yet. CSV and XLSX are available now."
    )


_WRITERS = {
    ReportFormat.CSV: _write_csv,
    ReportFormat.XLSX: _write_xlsx,
    ReportFormat.PDF: _write_pdf,
}


# ---------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------

def get_report(report_id: int) -> GeneratedReport:
    report = GeneratedReport.query.get(report_id)
    if report is None:
        raise NotFoundError(f"Report {report_id} not found")
    return report


def list_reports(clinic_id: int | None = None) -> list[GeneratedReport]:
    query = GeneratedReport.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    return query.order_by(GeneratedReport.created_at.desc()).all()


@transactional
def generate_report(report_type: ReportType, report_format: ReportFormat,
                     clinic_id: int | None = None, generated_by_id: int | None = None,
                     filters: dict | None = None, storage_dir: str = "generated_reports") -> GeneratedReport:
    """
    Gathers live data (per report_type), exports it (per report_format),
    writes the file to disk, and logs a GeneratedReport record pointing
    at it. The report DATA itself is never stored in the DB — only the
    export artifact and its metadata, per your model's own docstring.

    NOTE: `storage_dir` currently means a local filesystem path — this
    is a placeholder. app/core/files is still an empty stub with no
    storage abstraction. Before this goes to production, file_url
    should point at real persistent storage (S3, GCS, etc.), and this
    function should call into core/files rather than write locally.
    """
    if report_type in _UNSUPPORTED_TYPES:
        raise NotImplementedError(
            f"Report type '{report_type.value}' requires staff_service/inventory_service, "
            f"which don't exist as usable code yet."
        )

    gatherer = _GATHERERS.get(report_type)
    if gatherer is None:
        raise ValidationError(f"Unsupported report type: {report_type.value}")

    writer = _WRITERS.get(report_format)
    if writer is None:
        raise ValidationError(f"Unsupported report format: {report_format.value}")

    filters = filters or {}
    headers, rows = gatherer(clinic_id, filters)
    file_bytes = writer(headers, rows)  # raises NotImplementedError for PDF today

    os.makedirs(storage_dir, exist_ok=True)
    filename = f"{report_type.value}_{_utcnow().strftime('%Y%m%d%H%M%S')}.{report_format.value}"
    file_path = os.path.join(storage_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    report = GeneratedReport(
        clinic_id=clinic_id,
        generated_by_id=generated_by_id,
        report_type=report_type,
        report_format=report_format,
        filters=filters,
        file_url=file_path,  # TODO: swap for a real storage URL once core/files exists
    )
    db.session.add(report)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="GeneratedReport",
        entity_id=report.id,
        description=f"Report '{report_type.value}' generated as {report_format.value} ({len(rows)} row(s))",
        new_value={"report_type": report_type.value, "format": report_format.value, "row_count": len(rows)},
    )
    return report