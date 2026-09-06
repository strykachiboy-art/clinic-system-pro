from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.ward_enums import (
    AdmissionStatus,
    BedStatus,
    ReservationStatus,
    WardType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.patient.models.patient_model import Patient
from app.modules.staff.models.staff_model import Staff

from app.modules.ward.models.ward_model import (
    Admission,
    Bed,
    BedReservation,
    Ward,
    WardTransfer,
)


def _utcnow():
    """
    Project-wide UTC timestamp helper.

    Ward models use timezone-aware UTC timestamps.
    """
    return datetime.now(timezone.utc)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def _validate_positive_id(value: int, field_name: str) -> int:
    if value is None:
        raise ValidationError(f"{field_name} is required")

    if not isinstance(value, int) or value <= 0:
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _validate_ward_type(ward_type):
    if ward_type is None:
        return WardType.GENERAL

    if isinstance(ward_type, WardType):
        return ward_type

    try:
        return WardType(ward_type)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid ward type: {ward_type}"
        )


def _validate_ward_capacity_value(capacity: int) -> int:
    if capacity is None:
        raise ValidationError("capacity is required")

    if not isinstance(capacity, int):
        raise ValidationError("capacity must be an integer")

    if capacity < 0:
        raise ValidationError(
            "capacity cannot be negative"
        )

    return capacity


def _validate_bed_number(bed_number: str) -> str:
    bed_number = _normalize_text(bed_number)

    if not bed_number:
        raise ValidationError(
            "bed_number is required"
        )

    if len(bed_number) > 30:
        raise ValidationError(
            "bed_number cannot exceed 30 characters"
        )

    return bed_number


def _validate_reason(reason: str | None) -> str | None:
    reason = _normalize_text(reason)

    if reason and len(reason) > 255:
        raise ValidationError(
            "reason cannot exceed 255 characters"
        )

    return reason


def _validate_clinic_id(clinic_id: int) -> int:
    return _validate_positive_id(
        clinic_id,
        "clinic_id",
    )


def _validate_actor_id(actor_user_id: int) -> int:
    return _validate_positive_id(
        actor_user_id,
        "actor_user_id",
    )


# ============================================================================
# OWNERSHIP / LOOKUP HELPERS
# ============================================================================


def _get_ward(
    ward_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Ward:
    ward_id = _validate_positive_id(
        ward_id,
        "ward_id",
    )

    query = Ward.query.filter(
        Ward.id == ward_id
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    ward = query.first()

    if ward is None:
        raise NotFoundError(
            f"Ward {ward_id} not found"
        )

    return ward


def _get_bed(
    bed_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Bed:
    bed_id = _validate_positive_id(
        bed_id,
        "bed_id",
    )

    query = (
        Bed.query
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(Bed.id == bed_id)
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    bed = query.first()

    if bed is None:
        raise NotFoundError(
            f"Bed {bed_id} not found"
        )

    return bed


def _get_patient(
    patient_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Patient:
    patient_id = _validate_positive_id(
        patient_id,
        "patient_id",
    )

    query = Patient.query.filter(
        Patient.id == patient_id
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Patient.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    patient = query.first()

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_staff(
    staff_id: int,
    clinic_id: int | None = None,
) -> Staff:
    staff_id = _validate_positive_id(
        staff_id,
        "staff_id",
    )

    query = Staff.query.filter(
        Staff.id == staff_id
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Staff.clinic_id == clinic_id
        )

    staff = query.first()

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def _get_reservation(
    reservation_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> BedReservation:
    reservation_id = _validate_positive_id(
        reservation_id,
        "reservation_id",
    )

    query = (
        BedReservation.query
        .join(Bed, BedReservation.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            BedReservation.id == reservation_id
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    reservation = query.first()

    if reservation is None:
        raise NotFoundError(
            f"Bed reservation {reservation_id} not found"
        )

    return reservation


def _get_admission(
    admission_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Admission:
    admission_id = _validate_positive_id(
        admission_id,
        "admission_id",
    )

    query = (
        Admission.query
        .join(Bed, Admission.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            Admission.id == admission_id
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    admission = query.first()

    if admission is None:
        raise NotFoundError(
            f"Admission {admission_id} not found"
        )

    return admission


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def _validate_staff_for_clinic(
    staff_id: int,
    clinic_id: int,
) -> Staff:
    staff = _get_staff(
        staff_id,
        clinic_id=clinic_id,
    )

    if staff.clinic_id != clinic_id:
        raise ConflictError(
            f"Staff {staff_id} does not belong to clinic {clinic_id}"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ConflictError(
            f"Staff {staff_id} is not active"
        )

    return staff


def _validate_patient_for_clinic(
    patient: Patient,
    clinic_id: int,
) -> Patient:
    if patient.clinic_id != clinic_id:
        raise ConflictError(
            f"Patient {patient.id} does not belong "
            f"to clinic {clinic_id}"
        )

    return patient


def _validate_bed_for_clinic(
    bed: Bed,
    clinic_id: int,
) -> Bed:
    if bed.ward is None:
        raise ConflictError(
            f"Bed {bed.id} is not assigned to a ward"
        )

    if bed.ward.clinic_id != clinic_id:
        raise ConflictError(
            f"Bed {bed.id} does not belong "
            f"to clinic {clinic_id}"
        )

    return bed


def _get_configured_bed_count(
    ward_id: int,
) -> int:
    return (
        db.session.query(
            func.count(Bed.id)
        )
        .filter(
            Bed.ward_id == ward_id
        )
        .scalar()
        or 0
    )


def _validate_ward_capacity(
    ward: Ward,
) -> None:
    bed_count = _get_configured_bed_count(
        ward.id
    )

    if bed_count > ward.capacity:
        raise ConflictError(
            f"Ward {ward.id} already has "
            f"{bed_count} beds configured against "
            f"a capacity of {ward.capacity}"
        )


def _validate_new_capacity(
    ward: Ward,
    new_capacity: int,
) -> None:
    bed_count = _get_configured_bed_count(
        ward.id
    )

    if new_capacity < bed_count:
        raise ConflictError(
            f"Capacity cannot be reduced below "
            f"the current configured bed count of {bed_count}"
        )


def _get_admission_clinic_id(
    admission: Admission,
) -> int:
    if admission.bed is None:
        raise ConflictError(
            f"Admission {admission.id} has no valid bed"
        )

    if admission.bed.ward is None:
        raise ConflictError(
            f"Admission {admission.id} has no valid ward"
        )

    return admission.bed.ward.clinic_id


# ============================================================================
# STATUS HELPERS
# ============================================================================


def _ensure_ward_active(
    clinic_id: int,
) -> None:
    ensure_clinic_active(clinic_id)


def _ensure_admission_active(
    admission: Admission,
) -> None:
    if admission.status != AdmissionStatus.ADMITTED:
        raise ConflictError(
            f"Admission {admission.id} is currently "
            f"'{admission.status.value}'"
        )


def _ensure_reservation_pending(
    reservation: BedReservation,
) -> None:
    if reservation.status != ReservationStatus.PENDING:
        raise ConflictError(
            f"Reservation {reservation.id} is currently "
            f"'{reservation.status.value}'"
        )


def _ensure_reservation_not_expired(
    reservation: BedReservation,
) -> None:
    if (
        reservation.expires_at is not None
        and reservation.expires_at <= _utcnow()
    ):
        raise ConflictError(
            f"Reservation {reservation.id} has expired"
        )


def _ensure_bed_available(
    bed: Bed,
) -> None:
    if bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed.id} is currently "
            f"'{bed.status.value}' and is not available"
        )


def _ensure_bed_occupied(
    bed: Bed,
) -> None:
    if bed.status != BedStatus.OCCUPIED:
        raise ConflictError(
            f"Bed {bed.id} is currently "
            f"'{bed.status.value}' and is not occupied"
        )


# ============================================================================
# ACTIVE RECORD HELPERS
# ============================================================================


def _get_active_admission_for_patient(
    patient_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> Admission | None:
    patient_id = _validate_positive_id(
        patient_id,
        "patient_id",
    )

    query = (
        Admission.query
        .join(Bed, Admission.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            Admission.patient_id == patient_id,
            Admission.status == AdmissionStatus.ADMITTED,
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    return query.first()


def _get_active_reservation_for_patient(
    patient_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> BedReservation | None:
    patient_id = _validate_positive_id(
        patient_id,
        "patient_id",
    )

    query = (
        BedReservation.query
        .join(Bed, BedReservation.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            BedReservation.patient_id == patient_id,
            BedReservation.status == ReservationStatus.PENDING,
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    return query.first()


def _get_active_reservation_for_bed(
    bed_id: int,
    clinic_id: int | None = None,
    lock: bool = False,
) -> BedReservation | None:
    bed_id = _validate_positive_id(
        bed_id,
        "bed_id",
    )

    query = (
        BedReservation.query
        .join(Bed, BedReservation.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            BedReservation.bed_id == bed_id,
            BedReservation.status == ReservationStatus.PENDING,
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(clinic_id)

        query = query.filter(
            Ward.clinic_id == clinic_id
        )

    if lock:
        query = query.with_for_update()

    return query.first()


def _get_latest_transfer(
    admission_id: int,
) -> WardTransfer | None:
    return (
        WardTransfer.query
        .filter(
            WardTransfer.admission_id == admission_id
        )
        .order_by(
            WardTransfer.transferred_at.desc(),
            WardTransfer.id.desc(),
        )
        .first()
    )


# ============================================================================
# WARD MANAGEMENT
# ============================================================================


def get_ward(
    ward_id: int,
    clinic_id: int | None = None,
) -> Ward:
    return _get_ward(
        ward_id,
        clinic_id=clinic_id,
    )


def list_wards(
    clinic_id: int,
    ward_type: WardType | str | None = None,
):
    clinic_id = _validate_clinic_id(clinic_id)

    _ensure_ward_active(clinic_id)

    query = Ward.query.filter(
        Ward.clinic_id == clinic_id
    )

    if ward_type is not None:
        ward_type = _validate_ward_type(
            ward_type
        )

        query = query.filter(
            Ward.ward_type == ward_type
        )

    return query.order_by(
        Ward.name.asc()
    ).all()


@transactional
def create_ward(
    clinic_id: int,
    name: str,
    ward_type: WardType,
    capacity: int,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(clinic_id)

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    _ensure_ward_active(clinic_id)

    name = _normalize_text(name)

    if not name:
        raise ValidationError(
            "Ward name is required"
        )

    if len(name) > 150:
        raise ValidationError(
            "Ward name cannot exceed 150 characters"
        )

    ward_type = _validate_ward_type(
        ward_type
    )

    capacity = _validate_ward_capacity_value(
        capacity
    )

    existing = Ward.query.filter(
        Ward.clinic_id == clinic_id,
        Ward.name == name,
    ).first()

    if existing is not None:
        raise ConflictError(
            f"Ward '{name}' already exists "
            f"in clinic {clinic_id}"
        )

    ward = Ward(
        clinic_id=clinic_id,
        name=name,
        ward_type=ward_type,
        capacity=capacity,
    )

    db.session.add(ward)
    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.CREATE,
        entity_type="ward",
        entity_id=ward.id,
        description=(
            f"Created ward '{ward.name}' "
            f"in clinic {clinic_id}"
        ),
    )

    return ward


@transactional
def update_ward(
    ward_id: int,
    clinic_id: int,
    actor_user_id: int | None = None,
    **fields,
):
    clinic_id = _validate_clinic_id(clinic_id)

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    _ensure_ward_active(clinic_id)

    ward = _get_ward(
        ward_id,
        clinic_id=clinic_id,
        lock=True,
    )

    old_value = {
        "name": ward.name,
        "ward_type": ward.ward_type.value,
        "capacity": ward.capacity,
    }

    if "name" in fields:
        name = _normalize_text(fields["name"])

        if not name:
            raise ValidationError(
                "Ward name cannot be empty"
            )

        if len(name) > 150:
            raise ValidationError(
                "Ward name cannot exceed 150 characters"
            )

        duplicate = (
            Ward.query
            .filter(
                Ward.clinic_id == clinic_id,
                Ward.name == name,
                Ward.id != ward.id,
            )
            .first()
        )

        if duplicate is not None:
            raise ConflictError(
                f"Ward '{name}' already exists "
                f"in clinic {clinic_id}"
            )

        ward.name = name

    if "ward_type" in fields:
        ward.ward_type = _validate_ward_type(
            fields["ward_type"]
        )

    if "capacity" in fields:
        new_capacity = _validate_ward_capacity_value(
            fields["capacity"]
        )

        _validate_new_capacity(
            ward,
            new_capacity,
        )

        ward.capacity = new_capacity

    db.session.flush()

    new_value = {
        "name": ward.name,
        "ward_type": ward.ward_type.value,
        "capacity": ward.capacity,
    }

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="ward",
        entity_id=ward.id,
        description=f"Updated ward {ward.id}",
        old_value=old_value,
        new_value=new_value,
    )

    return ward


def get_ward_occupancy(
    ward_id: int,
    clinic_id: int,
):
    clinic_id = _validate_clinic_id(clinic_id)

    ward = _get_ward(
        ward_id,
        clinic_id=clinic_id,
    )

    total_beds = len(ward.beds)

    occupied = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.OCCUPIED
    )

    available = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.AVAILABLE
    )

    reserved = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.RESERVED
    )

    maintenance = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.MAINTENANCE
    )

    return {
        "ward_id": ward.id,
        "clinic_id": ward.clinic_id,
        "ward_name": ward.name,
        "capacity": ward.capacity,
        "total_beds": total_beds,
        "occupied": occupied,
        "available": available,
        "reserved": reserved,
        "maintenance": maintenance,
    }


# ============================================================================
# BED MANAGEMENT
# ============================================================================


def get_bed(
    bed_id: int,
    clinic_id: int | None = None,
) -> Bed:
    return _get_bed(
        bed_id,
        clinic_id=clinic_id,
    )


def list_beds(
    ward_id: int,
    clinic_id: int,
    status: BedStatus | str | None = None,
):
    clinic_id = _validate_clinic_id(clinic_id)

    ward = _get_ward(
        ward_id,
        clinic_id=clinic_id,
    )

    query = Bed.query.filter(
        Bed.ward_id == ward.id
    )

    if status is not None:
        try:
            if not isinstance(status, BedStatus):
                status = BedStatus(status)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Invalid bed status: {status}"
            )

        query = query.filter(
            Bed.status == status
        )

    return query.order_by(
        Bed.bed_number.asc()
    ).all()


@transactional
def add_bed(
    ward_id: int,
    bed_number: str,
    clinic_id: int,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(clinic_id)

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    ward = _get_ward(
        ward_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_ward_active(
        ward.clinic_id
    )

    bed_number = _validate_bed_number(
        bed_number
    )

    current_count = _get_configured_bed_count(
        ward.id
    )

    if current_count >= ward.capacity:
        raise ConflictError(
            f"Ward {ward.id} has reached "
            f"its configured capacity of {ward.capacity}"
        )

    existing = Bed.query.filter(
        Bed.ward_id == ward.id,
        Bed.bed_number == bed_number,
    ).first()

    if existing is not None:
        raise ConflictError(
            f"Bed '{bed_number}' already exists "
            f"in ward {ward.id}"
        )

    bed = Bed(
        ward_id=ward.id,
        bed_number=bed_number,
        status=BedStatus.AVAILABLE,
    )

    db.session.add(bed)
    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.CREATE,
        entity_type="bed",
        entity_id=bed.id,
        description=(
            f"Added bed '{bed.bed_number}' "
            f"to ward {ward.id}"
        ),
    )

    return bed


@transactional
def set_bed_maintenance(
    bed_id: int,
    under_maintenance: bool,
    clinic_id: int,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(clinic_id)

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    bed = _get_bed(
        bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    _ensure_ward_active(
        clinic_id
    )

    if not isinstance(
        under_maintenance,
        bool,
    ):
        raise ValidationError(
            "under_maintenance must be boolean"
        )

    old_status = bed.status

    if under_maintenance:
        if bed.status in (
            BedStatus.OCCUPIED,
            BedStatus.RESERVED,
        ):
            raise ConflictError(
                f"Bed {bed.id} cannot be placed "
                f"under maintenance while "
                f"'{bed.status.value}'"
            )

        bed.status = BedStatus.MAINTENANCE

    else:
        if bed.status != BedStatus.MAINTENANCE:
            raise ConflictError(
                f"Bed {bed.id} is not under maintenance"
            )

        bed.status = BedStatus.AVAILABLE

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="bed",
        entity_id=bed.id,
        description=(
            f"Changed bed {bed.id} maintenance status"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": bed.status.value,
        },
    )

    return bed


# ============================================================================
# BED RESERVATIONS
# ============================================================================


def get_bed_reservation(
    reservation_id: int,
    clinic_id: int | None = None,
) -> BedReservation:
    return _get_reservation(
        reservation_id,
        clinic_id=clinic_id,
    )


def list_bed_reservations(
    clinic_id: int,
    status: ReservationStatus | str | None = None,
    patient_id: int | None = None,
    bed_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    query = (
        BedReservation.query
        .join(Bed, BedReservation.bed_id == Bed.id)
        .join(Ward, Bed.ward_id == Ward.id)
        .filter(
            Ward.clinic_id == clinic_id
        )
    )

    if status is not None:
        try:
            if not isinstance(
                status,
                ReservationStatus,
            ):
                status = ReservationStatus(
                    status
                )
        except (TypeError, ValueError):
            raise ValidationError(
                f"Invalid reservation status: {status}"
            )

        query = query.filter(
            BedReservation.status == status
        )

    if patient_id is not None:
        patient_id = _validate_positive_id(
            patient_id,
            "patient_id",
        )

        query = query.filter(
            BedReservation.patient_id == patient_id
        )

    if bed_id is not None:
        bed_id = _validate_positive_id(
            bed_id,
            "bed_id",
        )

        query = query.filter(
            BedReservation.bed_id == bed_id
        )

    return query.order_by(
        BedReservation.reserved_at.desc()
    ).all()


def get_active_bed_reservation_for_patient(
    patient_id: int,
    clinic_id: int,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    _get_patient(
        patient_id,
        clinic_id=clinic_id,
    )

    return _get_active_reservation_for_patient(
        patient_id,
        clinic_id=clinic_id,
    )


def get_active_bed_reservation_for_bed(
    bed_id: int,
    clinic_id: int,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    _get_bed(
        bed_id,
        clinic_id=clinic_id,
    )

    return _get_active_reservation_for_bed(
        bed_id,
        clinic_id=clinic_id,
    )


@transactional
def reserve_bed(
    patient_id: int,
    bed_id: int,
    reserved_by_id: int,
    clinic_id: int,
    reason: str | None = None,
    expires_at=None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    reserved_by_id = _validate_positive_id(
        reserved_by_id,
        "reserved_by_id",
    )

    if actor_user_id is None:
        actor_user_id = reserved_by_id

    actor_user_id = _validate_actor_id(
        actor_user_id
    )

    _ensure_ward_active(
        clinic_id
    )

    patient = _get_patient(
        patient_id,
        clinic_id=clinic_id,
        lock=True,
    )

    bed = _get_bed(
        bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_patient_for_clinic(
        patient,
        clinic_id,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    # The actor is authenticated and must correspond
    # to an active staff member in this clinic.
    staff = _validate_staff_for_clinic(
        reserved_by_id,
        clinic_id,
    )

    if staff.user_id != actor_user_id:
        raise ConflictError(
            "Reservation actor does not match "
            "the authenticated user"
        )

    if expires_at is not None:
        if expires_at <= _utcnow():
            raise ValidationError(
                "expires_at must be in the future"
            )

    reason = _validate_reason(
        reason
    )

    active_admission = _get_active_admission_for_patient(
        patient.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"an active admission"
        )

    active_reservation = _get_active_reservation_for_patient(
        patient.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if active_reservation is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"an active bed reservation"
        )

    bed_reservation = _get_active_reservation_for_bed(
        bed.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if bed_reservation is not None:
        raise ConflictError(
            f"Bed {bed.id} already has "
            f"an active reservation"
        )

    _ensure_bed_available(
        bed
    )

    reservation = BedReservation(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=staff.id,
        status=ReservationStatus.PENDING,
        reason=reason,
        reserved_at=_utcnow(),
        expires_at=expires_at,
    )

    db.session.add(reservation)

    bed.status = BedStatus.RESERVED

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.CREATE,
        entity_type="bed_reservation",
        entity_id=reservation.id,
        description=(
            f"Reserved bed {bed.id} "
            f"for patient {patient.id}"
        ),
    )

    return reservation


@transactional
def cancel_bed_reservation(
    reservation_id: int,
    clinic_id: int,
    reason: str | None = None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    _ensure_ward_active(
        clinic_id
    )

    reservation = _get_reservation(
        reservation_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_reservation_pending(
        reservation
    )

    bed = _get_bed(
        reservation.bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    reason = _validate_reason(
        reason
    )

    reservation.status = (
        ReservationStatus.CANCELLED
    )
    reservation.cancelled_at = _utcnow()

    if reason:
        reservation.reason = reason

    if bed.status == BedStatus.RESERVED:
        bed.status = BedStatus.AVAILABLE

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="bed_reservation",
        entity_id=reservation.id,
        description=(
            f"Cancelled bed reservation "
            f"{reservation.id}"
        ),
        new_value={
            "status": reservation.status.value,
            "cancelled_at": (
                reservation.cancelled_at.isoformat()
                if reservation.cancelled_at
                else None
            ),
        },
    )

    return reservation


@transactional
def expire_bed_reservation(
    reservation_id: int,
):
    reservation = _get_reservation(
        reservation_id,
        lock=True,
    )

    if reservation.status != ReservationStatus.PENDING:
        return reservation

    now = _utcnow()

    if (
        reservation.expires_at is None
        or reservation.expires_at > now
    ):
        return reservation

    bed = _get_bed(
        reservation.bed_id,
        lock=True,
    )

    reservation.status = (
        ReservationStatus.EXPIRED
    )

    if bed.status == BedStatus.RESERVED:
        bed.status = BedStatus.AVAILABLE

    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="bed_reservation",
        entity_id=reservation.id,
        description=(
            f"Expired bed reservation "
            f"{reservation.id}"
        ),
    )

    return reservation


@transactional
def expire_due_bed_reservations(
    clinic_id: int | None = None,
):
    query = (
        BedReservation.query
        .filter(
            BedReservation.status
            == ReservationStatus.PENDING,
            BedReservation.expires_at.isnot(None),
            BedReservation.expires_at <= _utcnow(),
        )
    )

    if clinic_id is not None:
        clinic_id = _validate_clinic_id(
            clinic_id
        )

        query = (
            query
            .join(
                Bed,
                BedReservation.bed_id == Bed.id,
            )
            .join(
                Ward,
                Bed.ward_id == Ward.id,
            )
            .filter(
                Ward.clinic_id == clinic_id
            )
        )

    reservations = query.with_for_update().all()

    for reservation in reservations:
        bed = _get_bed(
            reservation.bed_id,
            clinic_id=clinic_id,
            lock=True,
        )

        reservation.status = (
            ReservationStatus.EXPIRED
        )

        if bed.status == BedStatus.RESERVED:
            bed.status = BedStatus.AVAILABLE

    return reservations


# ============================================================================
# ADMISSIONS
# ============================================================================


def get_admission(
    admission_id: int,
    clinic_id: int | None = None,
):
    return _get_admission(
        admission_id,
        clinic_id=clinic_id,
    )


def get_active_admission_for_patient(
    patient_id: int,
    clinic_id: int,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    _get_patient(
        patient_id,
        clinic_id=clinic_id,
    )

    return _get_active_admission_for_patient(
        patient_id,
        clinic_id=clinic_id,
    )


def list_admissions_for_patient(
    patient_id: int,
    clinic_id: int,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    _get_patient(
        patient_id,
        clinic_id=clinic_id,
    )

    return (
        Admission.query
        .join(
            Bed,
            Admission.bed_id == Bed.id,
        )
        .join(
            Ward,
            Bed.ward_id == Ward.id,
        )
        .filter(
            Admission.patient_id == patient_id,
            Ward.clinic_id == clinic_id,
        )
        .order_by(
            Admission.admitted_at.desc()
        )
        .all()
    )


def get_current_bed(
    patient_id: int,
    clinic_id: int,
):
    admission = get_active_admission_for_patient(
        patient_id,
        clinic_id,
    )

    if admission is None:
        return None

    return admission.bed


@transactional
def admit_patient(
    patient_id: int,
    bed_id: int,
    admitted_by_id: int,
    clinic_id: int,
    reason: str | None = None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    admitted_by_id = _validate_positive_id(
        admitted_by_id,
        "admitted_by_id",
    )

    if actor_user_id is None:
        actor_user_id = admitted_by_id

    actor_user_id = _validate_actor_id(
        actor_user_id
    )

    _ensure_ward_active(
        clinic_id
    )

    # Lock patient first.
    patient = _get_patient(
        patient_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_patient_for_clinic(
        patient,
        clinic_id,
    )

    active_admission = _get_active_admission_for_patient(
        patient.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"an active admission"
        )

    active_reservation = _get_active_reservation_for_patient(
        patient.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if active_reservation is not None:
        raise ConflictError(
            f"Patient {patient.id} has an active "
            f"reservation that must be fulfilled "
            f"or cancelled first"
        )

    # Then lock the bed.
    bed = _get_bed(
        bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    _ensure_bed_available(
        bed
    )

    staff = _validate_staff_for_clinic(
        admitted_by_id,
        clinic_id,
    )

    if staff.user_id != actor_user_id:
        raise ConflictError(
            "Admission actor does not match "
            "the authenticated user"
        )

    reason = _validate_reason(
        reason
    )

    admission = Admission(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=staff.id,
        reservation_id=None,
        status=AdmissionStatus.ADMITTED,
        reason=reason,
        admitted_at=_utcnow(),
    )

    db.session.add(admission)

    bed.status = BedStatus.OCCUPIED

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.CREATE,
        entity_type="admission",
        entity_id=admission.id,
        description=(
            f"Admitted patient {patient.id} "
            f"to bed {bed.id}"
        ),
    )

    return admission


@transactional
def admit_patient_from_reservation(
    reservation_id: int,
    admitted_by_id: int,
    clinic_id: int,
    reason: str | None = None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    admitted_by_id = _validate_positive_id(
        admitted_by_id,
        "admitted_by_id",
    )

    if actor_user_id is None:
        actor_user_id = admitted_by_id

    actor_user_id = _validate_actor_id(
        actor_user_id
    )

    _ensure_ward_active(
        clinic_id
    )

    reservation = _get_reservation(
        reservation_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_reservation_pending(
        reservation
    )

    _ensure_reservation_not_expired(
        reservation
    )

    # Lock patient before bed, matching the direct
    # admission workflow.
    patient = _get_patient(
        reservation.patient_id,
        clinic_id=clinic_id,
        lock=True,
    )

    bed = _get_bed(
        reservation.bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_patient_for_clinic(
        patient,
        clinic_id,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    staff = _validate_staff_for_clinic(
        admitted_by_id,
        clinic_id,
    )

    if staff.user_id != actor_user_id:
        raise ConflictError(
            "Admission actor does not match "
            "the authenticated user"
        )

    active_admission = _get_active_admission_for_patient(
        patient.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"an active admission"
        )

    active_reservation = _get_active_reservation_for_bed(
        bed.id,
        clinic_id=clinic_id,
        lock=True,
    )

    if (
        active_reservation is None
        or active_reservation.id != reservation.id
    ):
        raise ConflictError(
            f"Reservation {reservation.id} "
            f"is no longer the active reservation "
            f"for bed {bed.id}"
        )

    if bed.status != BedStatus.RESERVED:
        raise ConflictError(
            f"Bed {bed.id} is currently "
            f"'{bed.status.value}' and is not reserved"
        )

    reason = _validate_reason(
        reason
    )

    admission = Admission(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=staff.id,
        reservation_id=reservation.id,
        status=AdmissionStatus.ADMITTED,
        reason=reason or reservation.reason,
        admitted_at=_utcnow(),
    )

    db.session.add(admission)

    reservation.status = (
        ReservationStatus.FULFILLED
    )
    reservation.fulfilled_at = _utcnow()

    bed.status = BedStatus.OCCUPIED

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.CREATE,
        entity_type="admission",
        entity_id=admission.id,
        description=(
            f"Admitted patient {patient.id} "
            f"from reservation {reservation.id}"
        ),
    )

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="bed_reservation",
        entity_id=reservation.id,
        description=(
            f"Fulfilled bed reservation "
            f"{reservation.id}"
        ),
    )

    return admission


# Backward-compatible alias.
fulfill_bed_reservation = (
    admit_patient_from_reservation
)


@transactional
def transfer_bed(
    admission_id: int,
    to_bed_id: int,
    clinic_id: int,
    reason: str | None = None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    _ensure_ward_active(
        clinic_id
    )

    admission = _get_admission(
        admission_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_admission_active(
        admission
    )

    source_bed_id = admission.bed_id

    if source_bed_id == to_bed_id:
        raise ValidationError(
            "Source and destination beds "
            "must be different"
        )

    # Lock beds in deterministic ID order to reduce
    # deadlock risk during concurrent transfers.
    first_bed_id, second_bed_id = sorted(
        [source_bed_id, to_bed_id]
    )

    first_bed = _get_bed(
        first_bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    second_bed = _get_bed(
        second_bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if first_bed.id == source_bed_id:
        from_bed = first_bed
        to_bed = second_bed
    else:
        from_bed = second_bed
        to_bed = first_bed

    _validate_bed_for_clinic(
        from_bed,
        clinic_id,
    )

    _validate_bed_for_clinic(
        to_bed,
        clinic_id,
    )

    if from_bed.status != BedStatus.OCCUPIED:
        raise ConflictError(
            f"Source bed {from_bed.id} is not occupied"
        )

    _ensure_bed_available(
        to_bed
    )

    reason = _validate_reason(
        reason
    )

    transfer = WardTransfer(
        admission_id=admission.id,
        from_bed_id=from_bed.id,
        to_bed_id=to_bed.id,
        reason=reason,
        transferred_at=_utcnow(),
    )

    db.session.add(transfer)

    from_bed.status = BedStatus.AVAILABLE
    to_bed.status = BedStatus.OCCUPIED

    admission.bed_id = to_bed.id

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="admission",
        entity_id=admission.id,
        description=(
            f"Transferred admission {admission.id} "
            f"from bed {from_bed.id} "
            f"to bed {to_bed.id}"
        ),
        old_value={
            "bed_id": from_bed.id,
        },
        new_value={
            "bed_id": to_bed.id,
        },
    )

    return transfer


@transactional
def discharge_patient(
    admission_id: int,
    clinic_id: int,
    reason: str | None = None,
    actor_user_id: int | None = None,
):
    clinic_id = _validate_clinic_id(
        clinic_id
    )

    if actor_user_id is not None:
        actor_user_id = _validate_actor_id(
            actor_user_id
        )

    _ensure_ward_active(
        clinic_id
    )

    admission = _get_admission(
        admission_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_admission_active(
        admission
    )

    bed = _get_bed(
        admission.bed_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_bed_for_clinic(
        bed,
        clinic_id,
    )

    _ensure_bed_occupied(
        bed
    )

    reason = _validate_reason(
        reason
    )

    admission.status = (
        AdmissionStatus.DISCHARGED
    )
    admission.discharged_at = _utcnow()

    if reason:
        admission.reason = reason

    bed.status = BedStatus.AVAILABLE

    db.session.flush()

    create_audit_log(
        user_id=actor_user_id,
        action=AuditAction.UPDATE,
        entity_type="admission",
        entity_id=admission.id,
        description=(
            f"Discharged patient "
            f"{admission.patient_id} "
            f"from admission {admission.id}"
        ),
        new_value={
            "status": admission.status.value,
            "discharged_at": (
                admission.discharged_at.isoformat()
                if admission.discharged_at
                else None
            ),
        },
    )

    return admission