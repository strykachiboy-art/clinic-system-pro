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
from app.core.exceptions import DomainError, NotFoundError, ValidationError
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
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    """Serialize date/datetime values to ISO format."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def _enum_value(value: Any) -> Any:
    """Return the underlying enum value when applicable."""
    return getattr(value, "value", value)


def _decimal_value(value: Any) -> Decimal:
    """
    Preserve monetary precision using Decimal.
    """
    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Report type / format coercion
# ---------------------------------------------------------------------------


def _coerce_report_type(
    value: ReportType | str,
) -> ReportType:
    """Coerce a report type into ReportType."""
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
    """Coerce a report format into ReportFormat."""
    if isinstance(value, ReportFormat):
        return value

    try:
        return ReportFormat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid report format: {value}"
        ) from exc


# ---------------------------------------------------------------------------
# Filter normalization
# ---------------------------------------------------------------------------


def _normalize_filter_date(
    field: str,
    value: Any,
) -> date | datetime:
    """
    Normalize a report filter date.

    ISO date strings become date objects.
    ISO datetime strings become datetime objects.
    Existing date/datetime values are preserved.
    """
    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            if len(value) == 10:
                return date.fromisoformat(value)

            return datetime.fromisoformat(value)

        except ValueError as exc:
            raise ValidationError(
                f"Invalid {field} value"
            ) from exc

    raise ValidationError(
        f"Invalid {field} value"
    )


def _compare_filter_dates(
    date_from: date | datetime,
    date_to: date | datetime,
) -> bool:
    """
    Compare date/datetime filter values safely.

    Date-only values are treated as calendar dates.
    Datetime values are compared as datetimes.
    Mixed date/datetime values are normalized to midnight
    for the date-only side.
    """
    if isinstance(date_from, datetime):
        normalized_from = date_from
    else:
        normalized_from = datetime.combine(
            date_from,
            time.min,
        )

    if isinstance(date_to, datetime):
        normalized_to = date_to
    else:
        normalized_to = datetime.combine(
            date_to,
            time.min,
        )

    return normalized_to < normalized_from


def _normalize_filters(
    filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Validate and normalize report filters.
    """
    if filters is None:
        return {}

    if not isinstance(filters, dict):
        raise ValidationError(
            "Report filters must be a dictionary"
        )

    unknown_fields = set(filters) - ALLOWED_FILTER_FIELDS

    if unknown_fields:
        raise ValidationError(
            "Unsupported report filter(s): "
            + ", ".join(
                sorted(
                    str(field)
                    for field in unknown_fields
                )
            )
        )

    normalized: dict[str, Any] = {}

    if "active_only" in filters:
        active_only = filters["active_only"]

        if isinstance(active_only, bool):
            normalized["active_only"] = active_only
        else:
            raise ValidationError(
                "active_only must be a boolean"
            )

    for field in DATE_FIELDS:
        if field not in filters:
            continue

        normalized[field] = _normalize_filter_date(
            field,
            filters[field],
        )

    date_from = normalized.get("date_from")
    date_to = normalized.get("date_to")

    if date_from is not None and date_to is not None:
        if _compare_filter_dates(
            date_from,
            date_to,
        ):
            raise ValidationError(
                "date_to must be greater than or equal to date_from"
            )

    return normalized


def _serialize_filters(
    filters: dict[str, Any],
) -> dict[str, Any]:
    """
    Serialize filters into JSON-safe values.
    """
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


# ---------------------------------------------------------------------------
# Datetime filtering
# ---------------------------------------------------------------------------


def _apply_datetime_range(
    query,
    column,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
):
    """
    Apply an inclusive date-range request using a half-open DB interval.

    date_from:
        inclusive

    date_to:
        inclusive when supplied as a date or midnight datetime.

    Examples:

        date_from=2026-09-01
        becomes:
            column >= 2026-09-01 00:00:00

        date_to=2026-09-08
        becomes:
            column < 2026-09-09 00:00:00

        date_to=2026-09-08T14:30:00
        becomes:
            column < 2026-09-08 14:30:00
    """
    if date_from is not None:
        if isinstance(date_from, datetime):
            start_datetime = date_from
        else:
            start_datetime = datetime.combine(
                date_from,
                time.min,
            )

        query = query.filter(
            column >= start_datetime
        )

    if date_to is not None:
        if isinstance(date_to, datetime):
            end_datetime = date_to

            if date_to.time() == time.min:
                end_datetime = (
                    date_to
                    + timedelta(days=1)
                )

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
# Authentication / authorization
# ---------------------------------------------------------------------------


def _get_requester(
    requester_user_id: int,
) -> Staff:
    """
    Resolve and validate the authenticated requester.

    The requester must:

    - have a valid positive integer ID
    - exist
    - have an active account
    - have an associated Staff record
    - have active staff status
    - have matching clinic assignments when both are present
    """
    if (
        isinstance(requester_user_id, bool)
        or not isinstance(requester_user_id, int)
        or requester_user_id <= 0
    ):
        raise ValidationError(
            "requester_user_id must be a positive integer"
        )

    user = db.session.get(
        User,
        requester_user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user not found"
        )

    if not getattr(
        user,
        "is_active",
        True,
    ):
        raise ValidationError(
            "Authenticated user account is inactive"
        )

    staff = getattr(
        user,
        "staff",
        None,
    )

    if staff is None:
        raise ValidationError(
            "Authenticated user is not associated with staff"
        )

    if _enum_value(
        staff.status
    ) != _enum_value(
        StaffStatus.ACTIVE
    ):
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
            "Authenticated user and staff clinic assignments "
            "do not match"
        )

    return staff


def _get_requester_clinic_id(
    requester: Staff,
) -> int | None:
    """
    Resolve the requester's effective clinic.
    """
    user = getattr(
        requester,
        "user",
        None,
    )

    user_clinic_id = (
        getattr(
            user,
            "clinic_id",
            None,
        )
        if user is not None
        else None
    )

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
            "Authenticated user and staff clinic assignments "
            "do not match"
        )

    clinic_id = (
        user_clinic_id
        if user_clinic_id is not None
        else staff_clinic_id
    )

    if clinic_id is None:
        return None

    if isinstance(
        clinic_id,
        bool,
    ):
        raise ValidationError(
            "Invalid authenticated clinic assignment"
        )

    try:
        clinic_id = int(clinic_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid authenticated clinic assignment"
        ) from exc

    if clinic_id <= 0:
        raise ValidationError(
            "Invalid authenticated clinic assignment"
        )

    return clinic_id


def _get_clinic(
    clinic_id: int,
) -> Clinic:
    """
    Resolve a clinic by primary key.
    """
    if (
        isinstance(clinic_id, bool)
        or not isinstance(clinic_id, int)
        or clinic_id <= 0
    ):
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
    """
    Return whether the clinic is active.
    """
    return (
        _enum_value(
            getattr(
                clinic,
                "status",
                None,
            )
        )
        == "active"
    )


def _require_active_clinic(
    clinic_id: int,
) -> Clinic:
    """
    Require an existing active clinic.
    """
    clinic = _get_clinic(
        clinic_id
    )

    if not _clinic_is_active(
        clinic
    ):
        raise ValidationError(
            f"Clinic {clinic.id} is inactive"
        )

    return clinic


def _resolve_clinic_scope(
    requester: Staff,
    requested_clinic_id: int | None,
) -> int | None:
    """
    Resolve the clinic scope available to the requester.

    Admin:
        - may explicitly select a clinic
        - may omit clinic_id for system-wide access

    Non-admin:
        - is always restricted to their own clinic
    """
    user = getattr(
        requester,
        "user",
        None,
    )

    role = getattr(
        user,
        "role",
        None,
    )

    is_admin = (
        _enum_value(role)
        == _enum_value(Role.ADMIN)
    )

    if is_admin:
        if requested_clinic_id is None:
            return None

        if (
            isinstance(
                requested_clinic_id,
                bool,
            )
            or not isinstance(
                requested_clinic_id,
                int,
            )
            or requested_clinic_id <= 0
        ):
            raise ValidationError(
                "clinic_id must be greater than zero"
            )

        _get_clinic(
            requested_clinic_id
        )

        return requested_clinic_id

    requester_clinic_id = (
        _get_requester_clinic_id(
            requester
        )
    )

    if requester_clinic_id is None:
        raise ValidationError(
            "Authenticated staff is not assigned to a clinic"
        )

    if requested_clinic_id is None:
        return requester_clinic_id

    if (
        isinstance(
            requested_clinic_id,
            bool,
        )
        or not isinstance(
            requested_clinic_id,
            int,
        )
        or requested_clinic_id <= 0
    ):
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    if (
        requested_clinic_id
        != requester_clinic_id
    ):
        raise ValidationError(
            "Unauthorized clinic access"
        )

    return requester_clinic_id


def _validate_report_generator(
    requester: Staff,
    clinic_id: int,
) -> Staff:
    """
    Validate that the authenticated requester may generate
    a report for the requested clinic.
    """
    if (
        isinstance(clinic_id, bool)
        or not isinstance(clinic_id, int)
        or clinic_id <= 0
    ):
        raise ValidationError(
            "clinic_id must be greater than zero"
        )

    user = getattr(
        requester,
        "user",
        None,
    )

    role = getattr(
        user,
        "role",
        None,
    )

    if (
        _enum_value(role)
        == _enum_value(Role.ADMIN)
    ):
        return requester

    requester_clinic_id = (
        _get_requester_clinic_id(
            requester
        )
    )

    if requester_clinic_id is None:
        raise ValidationError(
            "Authenticated staff is not assigned to a clinic"
        )

    if requester_clinic_id != clinic_id:
        raise ValidationError(
            "Unauthorized clinic access"
        )

    return requester


# ---------------------------------------------------------------------------
# Report gatherers
# ---------------------------------------------------------------------------


def _gather_patients(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Patient.query.filter(
        Patient.clinic_id == clinic_id
    )

    if (
        filters.get("active_only") is True
        and hasattr(
            Patient,
            "is_active",
        )
    ):
        query = query.filter(
            Patient.is_active.is_(True)
        )

    if hasattr(
        Patient,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            Patient.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        Patient.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for patient in query.all():
        rows.append(
            {
                "id": patient.id,
                "clinic_id": patient.clinic_id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "email": patient.email,
                "phone": patient.phone,
                "created_at": _iso(
                    getattr(
                        patient,
                        "created_at",
                        None,
                    )
                ),
            }
        )

    return rows


def _gather_staff(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Staff.query.filter(
        Staff.clinic_id == clinic_id
    )

    if filters.get(
        "active_only"
    ) is True:
        query = query.filter(
            Staff.status
            == StaffStatus.ACTIVE
        )

    if hasattr(
        Staff,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            Staff.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        Staff.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for staff in query.all():
        rows.append(
            {
                "id": staff.id,
                "clinic_id": staff.clinic_id,
                "user_id": getattr(
                    staff,
                    "user_id",
                    None,
                ),
                "first_name": getattr(
                    staff,
                    "first_name",
                    None,
                ),
                "last_name": getattr(
                    staff,
                    "last_name",
                    None,
                ),
                "specialty": getattr(
                    staff,
                    "specialty",
                    None,
                ),
                "phone": getattr(
                    staff,
                    "phone",
                    None,
                ),
                "email": getattr(
                    staff,
                    "email",
                    None,
                ),
                "status": _enum_value(
                    getattr(
                        staff,
                        "status",
                        None,
                    )
                ),
                "hired_at": _iso(
                    getattr(
                        staff,
                        "hired_at",
                        None,
                    )
                ),
                "created_at": _iso(
                    getattr(
                        staff,
                        "created_at",
                        None,
                    )
                ),
            }
        )

    return rows


def _gather_appointments(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Appointment.query.filter(
        Appointment.clinic_id == clinic_id
    )

    if hasattr(
        Appointment,
        "scheduled_start",
    ):
        query = _apply_datetime_range(
            query,
            Appointment.scheduled_start,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        Appointment.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for appointment in query.all():
        rows.append(
            {
                "id": appointment.id,
                "clinic_id": appointment.clinic_id,
                "patient_id": getattr(
                    appointment,
                    "patient_id",
                    None,
                ),
                "staff_id": getattr(
                    appointment,
                    "staff_id",
                    None,
                ),
                "status": _enum_value(
                    getattr(
                        appointment,
                        "status",
                        None,
                    )
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
        )

    return rows


def _gather_billing(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Invoice.query.filter(
        Invoice.clinic_id == clinic_id
    )

    if hasattr(
        Invoice,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            Invoice.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        Invoice.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for invoice in query.all():
        total_amount = _decimal_value(
            getattr(
                invoice,
                "total_amount",
                0,
            )
        )

        amount_paid = _decimal_value(
            getattr(
                invoice,
                "amount_paid",
                0,
            )
        )

        balance = (
            total_amount
            - amount_paid
        )

        rows.append(
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
                    getattr(
                        invoice,
                        "status",
                        None,
                    )
                ),
                "total_amount": total_amount,
                "amount_paid": amount_paid,
                "balance": balance,
                "created_at": _iso(
                    getattr(
                        invoice,
                        "created_at",
                        None,
                    )
                ),
            }
        )

    return rows


def _gather_lab(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = LabOrder.query.filter(
        LabOrder.clinic_id == clinic_id
    )

    if hasattr(
        LabOrder,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            LabOrder.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        LabOrder.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for order in query.all():
        rows.append(
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
                    getattr(
                        order,
                        "status",
                        None,
                    )
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
        )

    return rows


def _gather_pharmacy(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    query = Drug.query.filter(
        Drug.clinic_id == clinic_id
    )

    if (
        filters.get("active_only") is True
        and hasattr(
            Drug,
            "is_active",
        )
    ):
        query = query.filter(
            Drug.is_active.is_(True)
        )

    if hasattr(
        Drug,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            Drug.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    query = query.order_by(
        Drug.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for drug in query.all():
        rows.append(
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
                        0,
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
        )

    return rows


def _gather_ward(
    clinic_id: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    ward_query = Ward.query.filter(
        Ward.clinic_id == clinic_id
    )

    if (
        filters.get("active_only") is True
        and hasattr(
            Ward,
            "is_active",
        )
    ):
        ward_query = ward_query.filter(
            Ward.is_active.is_(True)
        )

    if hasattr(
        Ward,
        "created_at",
    ):
        ward_query = _apply_datetime_range(
            ward_query,
            Ward.created_at,
            filters.get("date_from"),
            filters.get("date_to"),
        )

    ward_query = ward_query.order_by(
        Ward.id.asc()
    )

    rows: list[dict[str, Any]] = []

    for ward in ward_query.all():
        beds = (
            Bed.query
            .filter(
                Bed.ward_id == ward.id
            )
            .order_by(
                Bed.id.asc()
            )
            .all()
        )

        admissions_query = (
            Admission.query
            .join(
                Bed,
                Admission.bed_id == Bed.id,
            )
            .filter(
                Bed.ward_id == ward.id
            )
        )

        if hasattr(
            Admission,
            "created_at",
        ):
            admissions_query = (
                _apply_datetime_range(
                    admissions_query,
                    Admission.created_at,
                    filters.get("date_from"),
                    filters.get("date_to"),
                )
            )

        admissions = (
            admissions_query.all()
        )

        reservations_query = (
            BedReservation.query
            .join(
                Bed,
                BedReservation.bed_id == Bed.id,
            )
            .filter(
                Bed.ward_id == ward.id
            )
        )

        if hasattr(
            BedReservation,
            "created_at",
        ):
            reservations_query = (
                _apply_datetime_range(
                    reservations_query,
                    BedReservation.created_at,
                    filters.get("date_from"),
                    filters.get("date_to"),
                )
            )

        reservations = (
            reservations_query.all()
        )

        available_count = 0
        occupied_count = 0
        reserved_count = 0
        maintenance_count = 0

        for bed in beds:
            status = _enum_value(
                getattr(
                    bed,
                    "status",
                    None,
                )
            )

            if status == "available":
                available_count += 1

            elif status == "occupied":
                occupied_count += 1

            elif status == "reserved":
                reserved_count += 1

            elif status == "maintenance":
                maintenance_count += 1

        rows.append(
            {
                "ward_id": ward.id,
                "clinic_id": ward.clinic_id,
                "ward_name": getattr(
                    ward,
                    "name",
                    None,
                ),
                "ward_type": _enum_value(
                    getattr(
                        ward,
                        "ward_type",
                        None,
                    )
                ),
                "capacity": getattr(
                    ward,
                    "capacity",
                    None,
                ),
                "total_beds": len(beds),
                "available_beds": available_count,
                "occupied_beds": occupied_count,
                "reserved_beds": reserved_count,
                "maintenance_beds": maintenance_count,
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

    billing = _gather_billing(
        clinic_id,
        filters,
    )

    lab = _gather_lab(
        clinic_id,
        filters,
    )

    pharmacy = _gather_pharmacy(
        clinic_id,
        filters,
    )

    ward = _gather_ward(
        clinic_id,
        filters,
    )

    total_billed = sum(
        (
            row["total_amount"]
            for row in billing
        ),
        Decimal("0"),
    )

    total_paid = sum(
        (
            row["amount_paid"]
            for row in billing
        ),
        Decimal("0"),
    )

    outstanding_balance = sum(
        (
            row["balance"]
            for row in billing
        ),
        Decimal("0"),
    )

    return [
        {
            "clinic_id": clinic_id,
            "patients": len(patients),
            "staff": len(staff),
            "appointments": len(appointments),
            "billing_records": len(billing),
            "lab_orders": len(lab),
            "pharmacy_items": len(pharmacy),
            "wards": len(ward),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "outstanding_balance": outstanding_balance,
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
# Report writers
# ---------------------------------------------------------------------------


def _writer_value(
    value: Any,
) -> Any:
    """
    Convert values into writer-safe representations.
    """
    if value is None:
        return ""

    if hasattr(
        value,
        "value",
    ):
        return value.value

    if isinstance(
        value,
        Decimal,
    ):
        return str(value)

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    return value


def _write_csv(
    rows: list[dict[str, Any]],
) -> bytes:
    """
    Generate CSV report content.
    """
    if not rows:
        return b"No data\n"

    output = io.StringIO(
        newline=""
    )

    fieldnames = list(
        rows[0].keys()
    )

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
    )

    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                key: _writer_value(
                    value
                )
                for key, value in row.items()
            }
        )

    return output.getvalue().encode(
        "utf-8"
    )


def _write_xlsx(
    rows: list[dict[str, Any]],
) -> bytes:
    """
    Generate XLSX report content.
    """
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
        worksheet.append(
            ["No data"]
        )

    else:
        fieldnames = list(
            rows[0].keys()
        )

        worksheet.append(
            fieldnames
        )

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

    workbook.save(
        output
    )

    return output.getvalue()


def _write_pdf(
    rows: list[dict[str, Any]],
) -> bytes:
    """
    Generate PDF report content.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import (
            A4,
            landscape,
        )
        from reportlab.lib.styles import (
            getSampleStyleSheet,
        )
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
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

    elements = [
        Paragraph(
            "Generated Report",
            styles["Title"],
        )
    ]

    if not rows:
        elements.append(
            Paragraph(
                "No data",
                styles["BodyText"],
            )
        )

    else:
        fieldnames = list(
            rows[0].keys()
        )

        table_data = [
            [
                Paragraph(
                    str(field),
                    styles["BodyText"],
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
                        styles["BodyText"],
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
                        colors.grey,
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.whitesmoke,
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
                ]
            )
        )

        elements.append(
            table
        )

    document.build(
        elements
    )

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
# File storage
# ---------------------------------------------------------------------------


def _save_report_file(
    clinic_id: int,
    report_type: ReportType,
    report_format: ReportFormat,
    content: bytes,
) -> str:
    """
    Persist a generated report atomically.

    A temporary file is written first and then atomically replaced
    into the final path.
    """
    extension = report_format.value

    unique_id = uuid4().hex

    filename = (
        f"clinic_{clinic_id}_"
        f"{report_type.value}_"
        f"{unique_id}.{extension}"
    )

    os.makedirs(
        DEFAULT_STORAGE_DIR,
        exist_ok=True,
    )

    final_path = os.path.join(
        DEFAULT_STORAGE_DIR,
        filename,
    )

    temp_path = (
        f"{final_path}.tmp"
    )

    try:
        with open(
            temp_path,
            "wb",
        ) as file:
            file.write(content)

        os.replace(
            temp_path,
            final_path,
        )

    except Exception:
        try:
            if os.path.exists(
                temp_path
            ):
                os.remove(
                    temp_path
                )
        except OSError:
            pass

        raise

    return final_path


def _delete_report_file(
    file_path: str | None,
) -> None:
    """
    Safely delete a generated report file.
    """
    if not file_path:
        return

    try:
        if os.path.exists(
            file_path
        ):
            os.remove(
                file_path
            )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Report retrieval
# ---------------------------------------------------------------------------


def get_report(
    report_id: int,
    requester_user_id: int,
) -> GeneratedReport:
    """
    Retrieve a single report subject to authorization.
    """
    if (
        isinstance(report_id, bool)
        or not isinstance(report_id, int)
        or report_id <= 0
    ):
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
        raise DomainError(
            f"Report {report_id} not found"
        )

    clinic_scope = _resolve_clinic_scope(
        requester,
        report.clinic_id,
    )

    if (
        clinic_scope is not None
        and report.clinic_id != clinic_scope
    ):
        raise ValidationError(
            "Unauthorized report access"
        )

    return report


def list_reports(
    requester_user_id: int,
    clinic_id: int | None = None,
    generated_by_id: int | None = None,
    report_type: ReportType | str | None = None,
    report_format: ReportFormat | str | None = None,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    List generated reports subject to clinic authorization and filters.
    """
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page <= 0
    ):
        raise ValidationError(
            "page must be greater than zero"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page < 1
        or per_page > 100
    ):
        raise ValidationError(
            "per_page must be between 1 and 100"
        )

    if clinic_id is not None:
        if (
            isinstance(
                clinic_id,
                bool,
            )
            or not isinstance(
                clinic_id,
                int,
            )
            or clinic_id <= 0
        ):
            raise ValidationError(
                "clinic_id must be greater than zero"
            )

    if generated_by_id is not None:
        if (
            isinstance(
                generated_by_id,
                bool,
            )
            or not isinstance(
                generated_by_id,
                int,
            )
            or generated_by_id <= 0
        ):
            raise ValidationError(
                "generated_by_id must be greater than zero"
            )

    if date_from is not None and not isinstance(
        date_from,
        (
            datetime,
            date,
        ),
    ):
        raise ValidationError(
            "Invalid date_from value"
        )

    if date_to is not None and not isinstance(
        date_to,
        (
            datetime,
            date,
        ),
    ):
        raise ValidationError(
            "Invalid date_to value"
        )

    if (
        date_from is not None
        and date_to is not None
        and _compare_filter_dates(
            date_from,
            date_to,
        )
    ):
        raise ValidationError(
            "date_to must be greater than or equal to date_from"
        )

    requester = _get_requester(
        requester_user_id
    )

    clinic_scope = _resolve_clinic_scope(
        requester,
        clinic_id,
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
        query = (
            query.join(
                Staff,
                GeneratedReport.generated_by_id
                == Staff.id,
            )
            .filter(
                Staff.clinic_id
                == clinic_scope
            )
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

    if hasattr(
        GeneratedReport,
        "created_at",
    ):
        query = _apply_datetime_range(
            query,
            GeneratedReport.created_at,
            date_from,
            date_to,
        )

        query = query.order_by(
            GeneratedReport.created_at.desc(),
            GeneratedReport.id.desc(),
        )

    else:
        query = query.order_by(
            GeneratedReport.id.desc()
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
    requester_user_id: int,
    clinic_id: int,
    report_type: ReportType | str,
    report_format: ReportFormat | str,
    filters: dict[str, Any] | None = None,
) -> GeneratedReport:
    """
    Generate, persist, and audit a report.

    The authenticated staff member is always used as generated_by_id.
    Client input cannot impersonate another staff member.
    """
    if (
        isinstance(clinic_id, bool)
        or not isinstance(clinic_id, int)
        or clinic_id <= 0
    ):
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
        requester,
        clinic_id,
    )

    _require_active_clinic(
        clinic_id
    )

    if report_type in _UNSUPPORTED_TYPES:
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "is not yet supported"
        )

    gatherer = _GATHERERS.get(
        report_type
    )

    if gatherer is None:
        raise ValidationError(
            f"No gatherer configured for "
            f"report type '{report_type.value}'"
        )

    if (
        report_format == ReportFormat.CSV
        and report_type not in SUPPORTED_CSV_TYPES
    ):
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "is not supported for CSV"
        )

    if (
        report_format == ReportFormat.XLSX
        and report_type not in SUPPORTED_XLSX_TYPES
    ):
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "is not supported for XLSX"
        )

    if (
        report_format == ReportFormat.PDF
        and report_type not in _SUPPORTED_PDF_TYPES
    ):
        raise ValidationError(
            f"Report type '{report_type.value}' "
            "is not supported for PDF"
        )

    normalized_filters = _normalize_filters(
        filters
    )

    rows = gatherer(
        clinic_id,
        normalized_filters,
    )

    writer = _WRITERS.get(
        report_format
    )

    if writer is None:
        raise ValidationError(
            "Unsupported report format: "
            f"{report_format.value}"
        )

    file_url: str | None = None

    try:
        content = writer(
            rows
        )

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

        db.session.add(
            report
        )

        db.session.flush()

        create_audit_log(
            action=AuditAction.CREATE,
            entity_type="GeneratedReport",
            entity_id=report.id,
            description=(
                "Report generated: "
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