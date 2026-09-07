from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.auth.user.models.user_model import User
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
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.lab.models.lab_model import LabOrder
from app.modules.patient.models.patient_model import Patient
from app.modules.pharmacy.models.pharmacy_model import Drug
from app.modules.reports.models.reports_model import GeneratedReport
from app.modules.staff.models.staff_model import Staff
from app.modules.ward.models.ward_model import (
    Admission,
    Bed,
    BedReservation,
    Ward,
)


DEFAULT_STORAGE_DIR = "generated_reports"


DATE_FIELDS = {
    "date_from",
    "date_to",
}


ALLOWED_FILTER_FIELDS = {
    "date_from",
    "date_to",
    "active_only",
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


_SUPPORTED_PDF_TYPES = SUPPORTED_CSV_TYPES


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


def _decimal_value(value: Any) -> Decimal | None:
    """
    Preserve monetary precision.

    Reports should not convert database Decimal values to float because
    binary floating-point can introduce rounding errors in financial data.
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def _coerce_report_type(
    value: ReportType | str,
) -> ReportType:
    if isinstance(value, ReportType):
        return value

    try:
        return ReportType(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid report type: {value}"
        ) from exc


def _coerce_report_format(
    value: ReportFormat | str,
) -> ReportFormat:
    if isinstance(value, ReportFormat):
        return value

    try:
        return ReportFormat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid report format: {value}"
        ) from exc


def _normalize_filters(
    filters: dict[str, Any] | None,
) -> dict[str, Any]:
    if not filters:
        return {}

    if not isinstance(filters, dict):
        raise ValidationError(
            "Report filters must be an object"
        )

    unknown_fields = set(filters) - ALLOWED_FILTER_FIELDS

    if unknown_fields:
        unknown = ", ".join(
            sorted(str(field) for field in unknown_fields)
        )
        raise ValidationError(
            f"Unsupported report filter(s): {unknown}"
        )

    normalized: dict[str, Any] = {}

    for key, value in filters.items():
        if value is None:
            continue

        if key == "active_only":
            if not isinstance(value, bool):
                raise ValidationError(
                    "active_only must be a boolean"
                )

            normalized[key] = value
            continue

        if key in DATE_FIELDS:
            if isinstance(value, datetime):
                normalized[key] = value
                continue

            if isinstance(value, date):
                normalized[key] = value
                continue

            if isinstance(value, str):
                if len(value) == 10:
                    try:
                        normalized[key] = date.fromisoformat(
                            value
                        )
                        continue
                    except ValueError:
                        pass

                try:
                    normalized[key] = datetime.fromisoformat(
                        value
                    )
                    continue
                except ValueError as exc:
                    raise ValidationError(
                        f"Invalid {key} value: {value}"
                    ) from exc

            raise ValidationError(
                f"Invalid {key} value"
            )

    date_from = normalized.get("date_from")
    date_to = normalized.get("date_to")

    if (
        date_from is not None
        and date_to is not None
        and date_to < date_from
    ):
        raise ValidationError(
            "date_to must be greater than or equal to date_from"
        )

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
        elif isinstance(value, Decimal):
            serialized[key] = str(value)
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
    Resolve the authenticated actor:

        JWT identity
            -> User
            -> Staff

    The authenticated User.id is the only trusted actor identity.
    """
    if not isinstance(requester_user_id, int):
        raise ValidationError(
            "Invalid authenticated user identity"
        )

    if requester_user_id <= 0:
        raise ValidationError(
            "Invalid authenticated user identity"
        )

    user = db.session.get(
        User,
        requester_user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ValidationError(
            "Authenticated user account is inactive"
        )

    staff = user.staff

    if staff is None:
        raise ValidationError(
            "Authenticated user is not linked to a staff record"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {staff.id} is inactive"
        )

    user_clinic_id = getattr(
        user,
        "clinic_id",
        None,
    )

    staff_clinic_id = getattr(
        staff,
        "clinic_id",
        None,
    )

    if (
        user_clinic_id is not None
        and staff_clinic_id is not None
        and user_clinic_id != staff_clinic_id
    ):
        raise ValidationError(
            "Authenticated user and staff clinic assignments do not match"
        )

    return staff


def _get_requester_clinic_id(
    requester: Staff,
) -> int | None:
    """
    Resolve the authenticated staff member's clinic.

    The User and Staff assignments must agree whenever both exist.
    """
    user = requester.user

    user_clinic_id = getattr(
        user,
        "clinic_id",
        None,
    ) if user is not None else None

    staff_clinic_id = getattr(
        requester,
        "clinic_id",
        None,
    )

    if (
        user_clinic_id is not None
        and staff_clinic_id is not None
        and user_clinic_id != staff_clinic_id
    ):
        raise ValidationError(
            "Authenticated user and staff clinic assignments do not match"
        )

    clinic_id = (
        user_clinic_id
        if user_clinic_id is not None
        else staff_clinic_id
    )

    if clinic_id is None:
        return None

    try:
        clinic_id = int(clinic_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Authenticated user has an invalid clinic assignment"
        ) from exc

    if clinic_id <= 0:
        raise ValidationError(
            "Authenticated user has an invalid clinic assignment"
        )

    return clinic_id


def _get_clinic(
    clinic_id: int,
) -> Clinic:
    if not isinstance(clinic_id, int) or clinic_id <= 0:
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _clinic_is_active(
    clinic: Clinic,
) -> bool:
    return _enum_value(
        getattr(clinic, "status", None)
    ) == "active"


def _require_active_clinic(
    clinic_id: int,
) -> Clinic:
    clinic = _get_clinic(clinic_id)

    if not _clinic_is_active(clinic):
        raise ValidationError(
            f"Clinic {clinic.id} is inactive"
        )

    return clinic


def _resolve_clinic_scope(
    *,
    requester: Staff,
    requested_clinic_id: int | None,
) -> int | None:
    """
    Determine the clinic scope available to the requester.

    Admin:
        - may explicitly select a clinic;
        - may omit clinic_id for system-wide report access.

    Non-admin:
        - must belong to a clinic;
        - omitted clinic_id means their own clinic;
        - another clinic is rejected.
    """
    user = requester.user

    if user is not None and user.role == Role.ADMIN:
        if requested_clinic_id is not None:
            _get_clinic(requested_clinic_id)

        return requested_clinic_id

    requester_clinic_id = _get_requester_clinic_id(
        requester
    )

    if requester_clinic_id is None:
        raise ValidationError(
            f"Staff {requester.id} is not assigned to a clinic"
        )

    if requested_clinic_id is None:
        return requester_clinic_id

    if requested_clinic_id != requester_clinic_id:
        raise ValidationError(
            "You are not authorized to access reports for "
            f"clinic {requested_clinic_id}"
        )

    return requester_clinic_id


def _validate_report_generator(
    *,
    requester: Staff,
    clinic_id: int,
) -> Staff:
    """
    The authenticated staff member is always the generator.

    generated_by_id is never accepted from the client.
    """
    if not isinstance(clinic_id, int):
        raise ValidationError(
            "clinic_id must be an integer"
        )

    if clinic_id <= 0:
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    user = requester.user

    if user is not None and user.role == Role.ADMIN:
        return requester

    requester_clinic_id = _get_requester_clinic_id(
        requester
    )

    if requester_clinic_id is None:
        raise ValidationError(
            f"Staff {requester.id} is not assigned to a clinic"
        )

    if requester_clinic_id != clinic_id:
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

    if hasattr(Patient, "created_at"):
        query = _apply_datetime_range(
            query,
            Patient.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
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

    if hasattr(Staff, "created_at"):
        query = _apply_datetime_range(
            query,
            Staff.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
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

    if hasattr(Drug, "created_at"):
        query = _apply_datetime_range(
            query,
            Drug.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
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
    ward_query = Ward.query.filter(
        Ward.clinic_id == clinic_id
    )

    if filters.get("active_only") is True:
        if hasattr(Ward, "is_active"):
            ward_query = ward_query.filter(
                Ward.is_active.is_(True)
            )

    if hasattr(Ward, "created_at"):
        ward_query = _apply_datetime_range(
            ward_query,
            Ward.created_at,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
        )

    wards = (
        ward_query
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

        admission_query = (
            Admission.query
            .join(
                Bed,
                Admission.bed_id == Bed.id,
            )
            .filter(
                Bed.ward_id == ward.id
            )
        )

        if hasattr(Admission, "created_at"):
            admission_query = _apply_datetime_range(
                admission_query,
                Admission.created_at,
                date_from=filters.get("date_from"),
                date_to=filters.get("date_to"),
            )

        admissions = admission_query.all()

        reservation_query = (
            BedReservation.query
            .join(
                Bed,
                BedReservation.bed_id == Bed.id,
            )
            .filter(
                Bed.ward_id == ward.id
            )
        )

        if hasattr(BedReservation, "created_at"):
            reservation_query = _apply_datetime_range(
                reservation_query,
                BedReservation.created_at,
                date_from=filters.get("date_from"),
                date_to=filters.get("date_to"),
            )

        reservations = reservation_query.all()

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
                    if _enum_value(
                        bed.status
                    ) == "available"
                ),
                "beds_occupied": sum(
                    1
                    for bed in beds
                    if _enum_value(
                        bed.status
                    ) == "occupied"
                ),
                "beds_reserved": sum(
                    1
                    for bed in beds
                    if _enum_value(
                        bed.status
                    ) == "reserved"
                ),
                "beds_maintenance": sum(
                    1
                    for bed in beds
                    if _enum_value(
                        bed.status
                    ) == "maintenance"
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
            row["total_amount"] or Decimal("0")
            for row in invoices
        ),
        Decimal("0"),
    )

    total_paid = sum(
        (
            row["amount_paid"] or Decimal("0")
            for row in invoices
        ),
        Decimal("0"),
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


def _writer_value(value: Any) -> Any:
    value = _enum_value(value)

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if value is None:
        return ""

    return value


def _write_csv(
    rows: list[dict[str, Any]],
) -> bytes:
    output = io.StringIO(
        newline="",
    )

    if not rows:
        output.write("No data\n")
        return output.getvalue().encode(
            "utf-8"
        )

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
                key: _writer_value(value)
                for key, value in row.items()
            }
        )

    return output.getvalue().encode(
        "utf-8"
    )


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
                    _writer_value(
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
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ValidationError(
            "PDF generation requires reportlab"
        ) from exc

    output = io.BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = styles["Heading1"]
    body_style = styles["BodyText"]

    story = [
        Paragraph(
            "Generated Report",
            title_style,
        ),
        Spacer(1, 5 * mm),
    ]

    if not rows:
        story.append(
            Paragraph(
                "No data",
                body_style,
            )
        )
    else:
        fieldnames = list(rows[0].keys())

        table_data = [
            [
                Paragraph(
                    str(field),
                    body_style,
                )
                for field in fieldnames
            ]
        ]

        for row in rows:
            table_data.append(
                [
                    Paragraph(
                        str(
                            _writer_value(
                                row.get(field)
                            )
                        ),
                        body_style,
                    )
                    for field in fieldnames
                ]
            )

        table = Table(
            table_data,
            repeatRows=1,
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.lightgrey,
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        7,
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        3,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        3,
                    ),
                ]
            )
        )

        story.append(table)

    document.build(story)

    return output.getvalue()


_WRITERS: dict[
    ReportFormat,
    Callable[
        [list[dict[str, Any]]],
        bytes,
    ],
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

    unique_id = uuid4().hex

    filename = (
        f"clinic_{clinic_id}_"
        f"{report_type.value}_"
        f"{unique_id}."
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

    temporary_path = (
        f"{file_path}.tmp"
    )

    try:
        with open(
            temporary_path,
            "wb",
        ) as file:
            file.write(content)

        os.replace(
            temporary_path,
            file_path,
        )
    except Exception:
        if os.path.exists(
            temporary_path
        ):
            try:
                os.remove(
                    temporary_path
                )
            except OSError:
                pass

        raise

    return file_path


def _delete_report_file(
    file_path: str | None,
) -> None:
    if not file_path:
        return

    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Report retrieval
# ---------------------------------------------------------------------------


def get_report(
    *,
    report_id: int,
    requester_user_id: int,
) -> GeneratedReport:
    if report_id <= 0:
        raise ValidationError(
            "report_id must be greater than zero"
        )

    requester = _get_requester(
        requester_user_id
    )

    report = db.session.get(
        GeneratedReport,
        report_id,
    )

    if report is None:
        raise NotFoundError(
            f"Report {report_id} not found"
        )

    clinic_scope = _resolve_clinic_scope(
        requester=requester,
        requested_clinic_id=report.clinic_id,
    )

    if (
        clinic_scope is not None
        and report.clinic_id != clinic_scope
    ):
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
    if page <= 0:
        raise ValidationError(
            "page must be greater than zero"
        )

    if per_page <= 0 or per_page > 100:
        raise ValidationError(
            "per_page must be between 1 and 100"
        )

    if clinic_id is not None and clinic_id <= 0:
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    if (
        generated_by_id is not None
        and generated_by_id <= 0
    ):
        raise ValidationError(
            "generated_by_id must be greater than zero"
        )

    if (
        date_from is not None
        and date_to is not None
        and date_to < date_from
    ):
        raise ValidationError(
            "date_to must be greater than or equal to date_from"
        )

    requester = _get_requester(
        requester_user_id
    )

    clinic_scope = _resolve_clinic_scope(
        requester=requester,
        requested_clinic_id=clinic_id,
    )

    if report_type is not None:
        report_type = _coerce_report_type(
            report_type
        )

    if report_format is not None:
        report_format = _coerce_report_format(
            report_format
        )

    query = GeneratedReport.query

    if clinic_scope is not None:
        query = query.filter(
            GeneratedReport.clinic_id
            == clinic_scope
        )

    if generated_by_id is not None:
        query = query.filter(
            GeneratedReport.generated_by_id
            == generated_by_id
        )

        if clinic_scope is not None:
            query = query.join(
                Staff,
                Staff.id
                == GeneratedReport.generated_by_id,
            ).filter(
                Staff.clinic_id
                == clinic_scope
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

    query = _apply_datetime_range(
        query,
        GeneratedReport.created_at,
        date_from=date_from,
        date_to=date_to,
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

    requester_user_id is the authenticated User.id from JWT.

    generated_by_id is always derived from the authenticated Staff record.

    The service deliberately accepts clinic_id because it must remain safe
    when called outside an HTTP route. Authorization is enforced here
    rather than trusting the caller.
    """
    if not isinstance(clinic_id, int):
        raise ValidationError(
            "clinic_id must be an integer"
        )

    if clinic_id <= 0:
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    report_type = _coerce_report_type(
        report_type
    )

    report_format = _coerce_report_format(
        report_format
    )

    requester = _get_requester(
        requester_user_id
    )

    generator = _validate_report_generator(
        requester=requester,
        clinic_id=clinic_id,
    )

    _require_active_clinic(
        clinic_id
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

    if report_format == ReportFormat.CSV:
        if report_type not in SUPPORTED_CSV_TYPES:
            raise ValidationError(
                "CSV generation is not supported for "
                f"report type '{report_type.value}'"
            )

    elif report_format == ReportFormat.XLSX:
        if report_type not in SUPPORTED_XLSX_TYPES:
            raise ValidationError(
                "XLSX generation is not supported for "
                f"report type '{report_type.value}'"
            )

    elif report_format == ReportFormat.PDF:
        if report_type not in _SUPPORTED_PDF_TYPES:
            raise ValidationError(
                "PDF generation is not supported for "
                f"report type '{report_type.value}'"
            )

    normalized_filters = _normalize_filters(
        filters
    )

    gatherer = _GATHERERS[
        report_type
    ]

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

    file_url: str | None = None

    try:
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
            user_id=requester_user_id,
        )

        return report

    except Exception:
        _delete_report_file(
            file_url
        )
        raise