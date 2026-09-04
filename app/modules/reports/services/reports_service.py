from __future__ import annotations

import csv
import io
import os

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from app.extensions import db

from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.reports_enums import ReportFormat, ReportType
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.appointment.models.appointment_model import Appointment
from app.modules.billing.models.billing_model import Invoice
from app.modules.lab.models.lab_model import LabOrder
from app.modules.patient.models.patient_model import Patient
from app.modules.pharmacy.models.pharmacy_model import Drug
from app.modules.staff.models.staff_model import Staff
from app.modules.ward.models.ward_model import (
    Admission,
    Bed,
    BedReservation,
    Ward,
)

from app.modules.reports.models.reports_model import GeneratedReport


DEFAULT_STORAGE_DIR = "generated_reports"


DATE_FIELDS = {
    "date_from",
    "date_to",
}


SUPPORTED_CSV_TYPES = {
    ReportType.OVERVIEW,
    ReportType.PATIENTS,
    ReportType.STAFF,
    ReportType.APPOINTMENTS,
    ReportType.BILLING,
    ReportType.LAB,
    ReportType.PHARMACY,
    ReportType.WARD,
}


SUPPORTED_XLSX_TYPES = SUPPORTED_CSV_TYPES


_UNSUPPORTED_TYPES = {
    ReportType.INVENTORY,
}


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def _enum_value(value: Any) -> Any:
    if value is None:
        return None

    return getattr(value, "value", value)


def _decimal_value(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def _normalize_filters(
    filters: dict[str, Any] | None,
) -> dict[str, Any]:
    if not filters:
        return {}

    normalized: dict[str, Any] = {}

    for key, value in filters.items():
        if value is None:
            continue

        if key in DATE_FIELDS and isinstance(value, str):
            if len(value) == 10:
                try:
                    normalized[key] = date.fromisoformat(value)
                    continue
                except ValueError:
                    pass

            try:
                normalized[key] = datetime.fromisoformat(value)
                continue
            except ValueError:
                raise ValidationError(
                    f"Invalid {key} value: {value}"
                )

        normalized[key] = value

    return normalized


def _serialize_filters(
    filters: dict[str, Any] | None,
) -> dict[str, Any]:
    if not filters:
        return {}

    serialized: dict[str, Any] = {}

    for key, value in filters.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, date):
            serialized[key] = value.isoformat()
        elif hasattr(value, "value"):
            serialized[key] = value.value
        else:
            serialized[key] = value

    return serialized


def _apply_datetime_range(
    query,
    column,
    *,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
):
    if date_from is not None:
        if isinstance(date_from, date) and not isinstance(
            date_from,
            datetime,
        ):
            start_datetime = datetime.combine(
                date_from,
                time.min,
            )
        else:
            start_datetime = date_from

        query = query.filter(
            column >= start_datetime
        )

    if date_to is not None:
        if isinstance(date_to, datetime):
            if (
                date_to.hour == 0
                and date_to.minute == 0
                and date_to.second == 0
                and date_to.microsecond == 0
            ):
                end_datetime = date_to + timedelta(days=1)
            else:
                end_datetime = date_to
        else:
            end_datetime = datetime.combine(
                date_to + timedelta(days=1),
                time.min,
            )

        query = query.filter(
            column < end_datetime
        )

    return query


# ---------------------------------------------------------------------------
# Authentication / authorization helpers
# ---------------------------------------------------------------------------


def _get_requester(
    requester_user_id: int,
) -> Staff:
    """
    Resolve the authenticated JWT User.id to the corresponding Staff record.

    JWT identity is User.id.

    Staff.user_id links the staff record to that user.
    """
    if not requester_user_id or requester_user_id <= 0:
        raise ValidationError(
            "Invalid authenticated user identity"
        )

    staff = (
        Staff.query
        .filter(
            Staff.user_id == requester_user_id,
        )
        .first()
    )

    if staff is None:
        raise ValidationError(
            "Authenticated user is not linked to a staff record"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {staff.id} is inactive"
        )

    return staff


def _resolve_clinic_scope(
    *,
    requester: Staff,
    requested_clinic_id: int | None,
) -> int | None:
    """
    Determine which clinic the requester may access.

    Admin:
        - Can specify a clinic.
        - Can omit clinic_id to access all clinics.

    Non-admin:
        - Must have a clinic.
        - Omitted clinic_id automatically means their own clinic.
        - Specified clinic_id must equal their own clinic.
    """
    user = requester.user

    if user is not None and user.role == Role.ADMIN:
        return requested_clinic_id

    if requester.clinic_id is None:
        raise ValidationError(
            f"Staff {requester.id} is not assigned to a clinic"
        )

    if requested_clinic_id is None:
        return requester.clinic_id

    if requested_clinic_id != requester.clinic_id:
        raise ValidationError(
            "You are not authorized to access reports for "
            f"clinic {requested_clinic_id}"
        )

    return requester.clinic_id


def _validate_report_generator(
    *,
    requester: Staff,
    clinic_id: int,
) -> Staff:
    """
    The authenticated staff member is always the report generator.

    We do not trust a generated_by_id supplied by the client.
    """
    if clinic_id is None:
        raise ValidationError(
            "clinic_id is required when generating a report"
        )

    if requester.user is not None and requester.user.role == Role.ADMIN:
        return requester

    if requester.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {requester.id} is not authorized to generate "
            f"reports for clinic {clinic_id}"
        )

    return requester


# ---------------------------------------------------------------------------
# Report gathering
# ---------------------------------------------------------------------------


def _gather_patients(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Patient.query.filter(
        Patient.clinic_id == clinic_id
    )

    if filters.get("active_only") is True:
        if hasattr(Patient, "is_active"):
            query = query.filter(
                Patient.is_active.is_(True)
            )

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    if hasattr(Patient, "created_at"):
        query = _apply_datetime_range(
            query,
            Patient.created_at,
            date_from=date_from,
            date_to=date_to,
        )

    patients = query.order_by(
        Patient.id.asc()
    ).all()

    return [
        {
            "id": patient.id,
            "clinic_id": patient.clinic_id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "email": patient.email,
            "phone": patient.phone,
            "created_at": _iso(
                getattr(patient, "created_at", None)
            ),
        }
        for patient in patients
    ]


def _gather_staff(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Staff.query.filter(
        Staff.clinic_id == clinic_id
    )

    if filters.get("active_only") is True:
        query = query.filter(
            Staff.status == StaffStatus.ACTIVE
        )

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    if hasattr(Staff, "created_at"):
        query = _apply_datetime_range(
            query,
            Staff.created_at,
            date_from=date_from,
            date_to=date_to,
        )

    staff_members = query.order_by(
        Staff.id.asc()
    ).all()

    return [
        {
            "id": staff.id,
            "clinic_id": staff.clinic_id,
            "user_id": staff.user_id,
            "first_name": staff.first_name,
            "last_name": staff.last_name,
            "specialty": staff.specialty,
            "phone": staff.phone,
            "email": staff.email,
            "status": _enum_value(staff.status),
            "hired_at": _iso(staff.hired_at),
            "created_at": _iso(staff.created_at),
        }
        for staff in staff_members
    ]


def _gather_appointments(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Appointment.query.filter(
        Appointment.clinic_id == clinic_id
    )

    if hasattr(Appointment, "scheduled_start"):
        query = _apply_datetime_range(
            query,
            Appointment.scheduled_start,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
        )

    appointments = query.order_by(
        Appointment.id.asc()
    ).all()

    return [
        {
            "id": appointment.id,
            "clinic_id": appointment.clinic_id,
            "patient_id": appointment.patient_id,
            "staff_id": appointment.staff_id,
            "status": _enum_value(
                getattr(appointment, "status", None)
            ),
            "scheduled_start": _iso(
                getattr(
                    appointment,
                    "scheduled_start",
                    None,
                )
            ),
            "scheduled_end": _iso(
                getattr(
                    appointment,
                    "scheduled_end",
                    None,
                )
            ),
            "created_at": _iso(
                getattr(
                    appointment,
                    "created_at",
                    None,
                )
            ),
        }
        for appointment in appointments
    ]


def _gather_billing(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Invoice.query.filter(
        Invoice.clinic_id == clinic_id
    )

    if hasattr(Invoice, "created_at"):
        query = _apply_datetime_range(
            query,
            Invoice.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
        )

    invoices = query.order_by(
        Invoice.id.asc()
    ).all()

    return [
        {
            "id": invoice.id,
            "clinic_id": invoice.clinic_id,
            "patient_id": getattr(
                invoice,
                "patient_id",
                None,
            ),
            "invoice_number": getattr(
                invoice,
                "invoice_number",
                None,
            ),
            "status": _enum_value(
                getattr(invoice, "status", None)
            ),
            "total_amount": _decimal_value(
                getattr(invoice, "total_amount", None)
            ),
            "amount_paid": _decimal_value(
                getattr(invoice, "amount_paid", None)
            ),
            "balance": _decimal_value(
                getattr(invoice, "balance", None)
            ),
            "created_at": _iso(
                getattr(invoice, "created_at", None)
            ),
        }
        for invoice in invoices
    ]


def _gather_lab(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = LabOrder.query.filter(
        LabOrder.clinic_id == clinic_id
    )

    if hasattr(LabOrder, "created_at"):
        query = _apply_datetime_range(
            query,
            LabOrder.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
        )

    orders = query.order_by(
        LabOrder.id.asc()
    ).all()

    return [
        {
            "id": order.id,
            "clinic_id": order.clinic_id,
            "patient_id": getattr(
                order,
                "patient_id",
                None,
            ),
            "ordered_by_id": getattr(
                order,
                "ordered_by_id",
                None,
            ),
            "status": _enum_value(
                getattr(order, "status", None)
            ),
            "test_name": getattr(
                order,
                "test_name",
                None,
            ),
            "completed_at": _iso(
                getattr(
                    order,
                    "completed_at",
                    None,
                )
            ),
            "created_at": _iso(
                getattr(
                    order,
                    "created_at",
                    None,
                )
            ),
        }
        for order in orders
    ]


def _gather_pharmacy(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Drug.query.filter(
        Drug.clinic_id == clinic_id
    )

    if filters.get("active_only") is True:
        if hasattr(Drug, "is_active"):
            query = query.filter(
                Drug.is_active.is_(True)
            )

    drugs = query.order_by(
        Drug.id.asc()
    ).all()

    return [
        {
            "id": drug.id,
            "clinic_id": drug.clinic_id,
            "name": getattr(
                drug,
                "name",
                None,
            ),
            "generic_name": getattr(
                drug,
                "generic_name",
                None,
            ),
            "quantity": getattr(
                drug,
                "quantity",
                None,
            ),
            "unit_price": _decimal_value(
                getattr(
                    drug,
                    "unit_price",
                    None,
                )
            ),
            "expiry_date": _iso(
                getattr(
                    drug,
                    "expiry_date",
                    None,
                )
            ),
            "created_at": _iso(
                getattr(
                    drug,
                    "created_at",
                    None,
                )
            ),
        }
        for drug in drugs
    ]


def _gather_ward(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    wards = (
        Ward.query
        .filter(
            Ward.clinic_id == clinic_id
        )
        .order_by(Ward.id.asc())
        .all()
    )

    rows: list[dict[str, Any]] = []

    for ward in wards:
        beds = (
            Bed.query
            .filter(
                Bed.ward_id == ward.id
            )
            .order_by(Bed.id.asc())
            .all()
        )

        admissions = (
            Admission.query
            .join(Bed, Admission.bed_id == Bed.id)
            .filter(
                Bed.ward_id == ward.id
            )
            .all()
        )

        reservations = (
            BedReservation.query
            .join(Bed, BedReservation.bed_id == Bed.id)
            .filter(
                Bed.ward_id == ward.id
            )
            .all()
        )

        rows.append(
            {
                "ward_id": ward.id,
                "clinic_id": ward.clinic_id,
                "ward_name": ward.name,
                "ward_type": _enum_value(
                    ward.ward_type
                ),
                "capacity": ward.capacity,
                "total_beds": len(beds),
                "beds_available": sum(
                    1
                    for bed in beds
                    if _enum_value(bed.status) == "available"
                ),
                "beds_occupied": sum(
                    1
                    for bed in beds
                    if _enum_value(bed.status) == "occupied"
                ),
                "beds_reserved": sum(
                    1
                    for bed in beds
                    if _enum_value(bed.status) == "reserved"
                ),
                "beds_maintenance": sum(
                    1
                    for bed in beds
                    if _enum_value(bed.status) == "maintenance"
                ),
                "admissions": len(admissions),
                "reservations": len(reservations),
                "created_at": _iso(
                    getattr(
                        ward,
                        "created_at",
                        None,
                    )
                ),
            }
        )

    return rows


def _gather_overview(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    patients = _gather_patients(
        clinic_id,
        filters,
    )

    staff = _gather_staff(
        clinic_id,
        filters,
    )

    appointments = _gather_appointments(
        clinic_id,
        filters,
    )

    invoices = _gather_billing(
        clinic_id,
        filters,
    )

    lab_orders = _gather_lab(
        clinic_id,
        filters,
    )

    pharmacy = _gather_pharmacy(
        clinic_id,
        filters,
    )

    wards = _gather_ward(
        clinic_id,
        filters,
    )

    total_billed = sum(
        (
            row["total_amount"] or 0
            for row in invoices
        ),
        0,
    )

    total_paid = sum(
        (
            row["amount_paid"] or 0
            for row in invoices
        ),
        0,
    )

    return [
        {
            "clinic_id": clinic_id,
            "patients": len(patients),
            "staff": len(staff),
            "appointments": len(appointments),
            "invoices": len(invoices),
            "lab_orders": len(lab_orders),
            "drugs": len(pharmacy),
            "wards": len(wards),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "outstanding_balance": (
                total_billed - total_paid
            ),
        }
    ]


_GATHERERS: dict[
    ReportType,
    Callable[
        [int, dict[str, Any]],
        list[dict[str, Any]],
    ],
] = {
    ReportType.OVERVIEW: _gather_overview,
    ReportType.PATIENTS: _gather_patients,
    ReportType.STAFF: _gather_staff,
    ReportType.APPOINTMENTS: _gather_appointments,
    ReportType.BILLING: _gather_billing,
    ReportType.LAB: _gather_lab,
    ReportType.PHARMACY: _gather_pharmacy,
    ReportType.WARD: _gather_ward,
}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _write_csv(
    rows: list[dict[str, Any]],
) -> bytes:
    output = io.StringIO()

    if not rows:
        output.write("No data\n")
        return output.getvalue().encode("utf-8")

    fieldnames = list(rows[0].keys())

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
    )

    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                key: _enum_value(value)
                for key, value in row.items()
            }
        )

    return output.getvalue().encode("utf-8")


def _write_xlsx(
    rows: list[dict[str, Any]],
) -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ValidationError(
            "XLSX generation requires openpyxl"
        ) from exc

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Report"

    if not rows:
        worksheet.append(["No data"])
    else:
        fieldnames = list(rows[0].keys())

        worksheet.append(fieldnames)

        for row in rows:
            worksheet.append(
                [
                    _enum_value(
                        row.get(field)
                    )
                    for field in fieldnames
                ]
            )

    output = io.BytesIO()

    workbook.save(output)

    return output.getvalue()


def _write_pdf(
    rows: list[dict[str, Any]],
) -> bytes:
    raise ValidationError(
        "PDF report generation is not yet implemented"
    )


_WRITERS: dict[
    ReportFormat,
    Callable[[list[dict[str, Any]]], bytes],
] = {
    ReportFormat.CSV: _write_csv,
    ReportFormat.XLSX: _write_xlsx,
    ReportFormat.PDF: _write_pdf,
}


# ---------------------------------------------------------------------------
# Report storage
# ---------------------------------------------------------------------------


def _save_report_file(
    *,
    clinic_id: int,
    report_type: ReportType,
    report_format: ReportFormat,
    content: bytes,
) -> str:
    extension = report_format.value

    timestamp = _utcnow().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    filename = (
        f"clinic_{clinic_id}_"
        f"{report_type.value}_"
        f"{timestamp}."
        f"{extension}"
    )

    os.makedirs(
        DEFAULT_STORAGE_DIR,
        exist_ok=True,
    )

    file_path = os.path.join(
        DEFAULT_STORAGE_DIR,
        filename,
    )

    with open(
        file_path,
        "wb",
    ) as file:
        file.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Report retrieval
# ---------------------------------------------------------------------------


def get_report(
    *,
    report_id: int,
    requester_user_id: int,
) -> GeneratedReport:
    requester = _get_requester(
        requester_user_id
    )

    report = GeneratedReport.query.get(
        report_id
    )

    if report is None:
        raise NotFoundError(
            f"Report {report_id} not found"
        )

    clinic_scope = _resolve_clinic_scope(
        requester=requester,
        requested_clinic_id=report.clinic_id,
    )

    if clinic_scope is not None:
        if report.clinic_id != clinic_scope:
            raise ValidationError(
                "You are not authorized to access this report"
            )

    return report


def list_reports(
    *,
    requester_user_id: int,
    clinic_id: int | None = None,
    generated_by_id: int | None = None,
    report_type: ReportType | None = None,
    report_format: ReportFormat | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    requester = _get_requester(
        requester_user_id
    )

    clinic_scope = _resolve_clinic_scope(
        requester=requester,
        requested_clinic_id=clinic_id,
    )

    query = GeneratedReport.query

    if clinic_scope is not None:
        query = query.filter(
            GeneratedReport.clinic_id == clinic_scope
        )

    if generated_by_id is not None:
        query = query.filter(
            GeneratedReport.generated_by_id
            == generated_by_id
        )

    if report_type is not None:
        query = query.filter(
            GeneratedReport.report_type
            == report_type
        )

    if report_format is not None:
        query = query.filter(
            GeneratedReport.report_format
            == report_format
        )

    if date_from is not None:
        start_datetime = datetime.combine(
            date_from,
            time.min,
        )

        query = query.filter(
            GeneratedReport.created_at
            >= start_datetime
        )

    if date_to is not None:
        end_datetime = datetime.combine(
            date_to + timedelta(days=1),
            time.min,
        )

        query = query.filter(
            GeneratedReport.created_at
            < end_datetime
        )

    query = query.order_by(
        GeneratedReport.created_at.desc(),
        GeneratedReport.id.desc(),
    )

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return {
        "items": pagination.items,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


@transactional
def generate_report(
    *,
    report_type: ReportType,
    report_format: ReportFormat,
    clinic_id: int,
    requester_user_id: int,
    filters: dict[str, Any] | None = None,
) -> GeneratedReport:
    """
    Generate and persist a report.

    requester_user_id is the authenticated User.id from the JWT.

    The service resolves:

        User.id
            ↓
        Staff.user_id
            ↓
        Staff.id

    Staff.id becomes GeneratedReport.generated_by_id.
    """
    if clinic_id <= 0:
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    requester = _get_requester(
        requester_user_id
    )

    generator = _validate_report_generator(
        requester=requester,
        clinic_id=clinic_id,
    )

    if report_type in _UNSUPPORTED_TYPES:
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "is not yet supported"
        )

    if report_type not in _GATHERERS:
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "does not have a configured data gatherer"
        )

    if report_format == ReportFormat.PDF:
        raise ValidationError(
            "PDF report generation is not yet implemented"
        )

    if report_format == ReportFormat.CSV:
        if report_type not in SUPPORTED_CSV_TYPES:
            raise ValidationError(
                f"CSV generation is not supported for "
                f"report type '{report_type.value}'"
            )

    if report_format == ReportFormat.XLSX:
        if report_type not in SUPPORTED_XLSX_TYPES:
            raise ValidationError(
                f"XLSX generation is not supported for "
                f"report type '{report_type.value}'"
            )

    normalized_filters = _normalize_filters(
        filters
    )

    gatherer = _GATHERERS[report_type]

    rows = gatherer(
        clinic_id,
        normalized_filters,
    )

    writer = _WRITERS.get(
        report_format
    )

    if writer is None:
        raise ValidationError(
            f"Report format '{report_format.value}' "
            "is not supported"
        )

    content = writer(rows)

    file_url = _save_report_file(
        clinic_id=clinic_id,
        report_type=report_type,
        report_format=report_format,
        content=content,
    )

    report = GeneratedReport(
        clinic_id=clinic_id,
        generated_by_id=generator.id,
        report_type=report_type,
        report_format=report_format,
        filters=_serialize_filters(
            normalized_filters
        ),
        file_url=file_url,
    )

    db.session.add(report)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="GeneratedReport",
        entity_id=report.id,
        description=(
            f"Report generated: "
            f"{report_type.value} / "
            f"{report_format.value} "
            f"for clinic {clinic_id}"
        ),
    )

    return report