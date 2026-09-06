from __future__ import annotations

from datetime import datetime, timezone

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


# ============================================================================
# Helpers
# ============================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def _validate_positive_id(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )


def _validate_ward_type(ward_type: WardType) -> None:
    if not isinstance(ward_type, WardType):
        try:
            WardType(ward_type)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"Invalid ward type '{ward_type}'"
            ) from exc


def _validate_ward_capacity_value(capacity: int) -> None:
    if not isinstance(capacity, int):
        raise ValidationError("Ward capacity must be an integer")

    if capacity < 0:
        raise ValidationError("Ward capacity cannot be negative")


def _validate_bed_number(bed_number: str) -> str:
    bed_number = _normalize_text(bed_number)

    if not bed_number:
        raise ValidationError("Bed number is required")

    if len(bed_number) > 30:
        raise ValidationError(
            "Bed number cannot exceed 30 characters"
        )

    return bed_number


def _validate_reason(reason: str | None) -> str | None:
    reason = _normalize_text(reason)

    if reason and len(reason) > 255:
        raise ValidationError(
            "Reason cannot exceed 255 characters"
        )

    return reason


def _get_ward(
    ward_id: int,
    *,
    lock: bool = False,
) -> Ward:
    _validate_positive_id(ward_id, "ward_id")

    query = Ward.query.filter_by(id=ward_id)

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
    *,
    lock: bool = False,
) -> Bed:
    _validate_positive_id(bed_id, "bed_id")

    query = Bed.query.filter_by(id=bed_id)

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
    *,
    lock: bool = False,
) -> Patient:
    _validate_positive_id(patient_id, "patient_id")

    query = Patient.query.filter_by(id=patient_id)

    if lock:
        query = query.with_for_update()

    patient = query.first()

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_staff(staff_id: int) -> Staff:
    _validate_positive_id(staff_id, "staff_id")

    staff = Staff.query.filter_by(id=staff_id).first()

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def _get_admission(
    admission_id: int,
    *,
    lock: bool = False,
) -> Admission:
    _validate_positive_id(admission_id, "admission_id")

    query = Admission.query.filter_by(id=admission_id)

    if lock:
        query = query.with_for_update()

    admission = query.first()

    if admission is None:
        raise NotFoundError(
            f"Admission {admission_id} not found"
        )

    return admission


def _get_reservation(
    reservation_id: int,
    *,
    lock: bool = False,
) -> BedReservation:
    _validate_positive_id(
        reservation_id,
        "reservation_id",
    )

    query = BedReservation.query.filter_by(
        id=reservation_id
    )

    if lock:
        query = query.with_for_update()

    reservation = query.first()

    if reservation is None:
        raise NotFoundError(
            f"Bed reservation {reservation_id} not found"
        )

    return reservation


def _validate_staff_for_clinic(
    *,
    staff_id: int,
    clinic_id: int,
) -> Staff:
    staff = _get_staff(staff_id)

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {staff_id} does not belong to clinic {clinic_id}"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ConflictError(
            f"Staff {staff_id} is inactive"
        )

    return staff


def _validate_patient_for_clinic(
    *,
    patient: Patient,
    clinic_id: int,
) -> None:
    if patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Patient {patient.id} does not belong to clinic {clinic_id}"
        )


def _validate_bed_for_clinic(
    *,
    bed: Bed,
    clinic_id: int,
) -> Ward:
    ward = bed.ward

    if ward is None:
        raise ValidationError(
            f"Bed {bed.id} is not associated with a ward"
        )

    if ward.clinic_id != clinic_id:
        raise ValidationError(
            f"Bed {bed.id} does not belong to clinic {clinic_id}"
        )

    return ward


def _get_configured_bed_count(ward_id: int) -> int:
    return (
        Bed.query
        .filter_by(ward_id=ward_id)
        .count()
    )


def _validate_ward_capacity(
    *,
    ward: Ward,
    capacity: int,
) -> None:
    _validate_ward_capacity_value(capacity)

    configured_beds = _get_configured_bed_count(
        ward.id
    )

    if capacity < configured_beds:
        raise ValidationError(
            f"Ward capacity cannot be less than the "
            f"configured bed count ({configured_beds})"
        )


def _validate_new_capacity(
    *,
    ward: Ward,
    new_capacity: int,
) -> None:
    _validate_ward_capacity(
        ward=ward,
        capacity=new_capacity,
    )


def _get_admission_clinic_id(
    admission: Admission,
) -> int:
    if admission.bed is None:
        raise ValidationError(
            f"Admission {admission.id} has no associated bed"
        )

    if admission.bed.ward is None:
        raise ValidationError(
            f"Admission {admission.id} has no associated ward"
        )

    return admission.bed.ward.clinic_id


def _assert_admission_active(
    admission: Admission,
) -> None:
    if admission.status != AdmissionStatus.ADMITTED:
        raise ConflictError(
            f"Admission {admission.id} is "
            f"'{admission.status.value}', not active"
        )


def _assert_reservation_pending(
    reservation: BedReservation,
) -> None:
    if reservation.status != ReservationStatus.PENDING:
        raise ConflictError(
            f"Reservation {reservation.id} is "
            f"'{reservation.status.value}', not pending"
        )


def _get_active_admission_for_patient_locked(
    patient_id: int,
) -> Admission | None:
    return (
        Admission.query
        .filter(
            Admission.patient_id == patient_id,
            Admission.status == AdmissionStatus.ADMITTED,
        )
        .with_for_update()
        .first()
    )


def _get_active_reservation_for_patient_locked(
    patient_id: int,
) -> BedReservation | None:
    return (
        BedReservation.query
        .filter(
            BedReservation.patient_id == patient_id,
            BedReservation.status == ReservationStatus.PENDING,
        )
        .with_for_update()
        .first()
    )


def _get_active_reservation_for_bed(
    bed_id: int,
) -> BedReservation | None:
    return (
        BedReservation.query
        .filter(
            BedReservation.bed_id == bed_id,
            BedReservation.status == ReservationStatus.PENDING,
        )
        .order_by(
            BedReservation.reserved_at.desc()
        )
        .first()
    )


def _get_latest_transfer(
    admission_id: int,
) -> WardTransfer | None:
    return (
        WardTransfer.query
        .filter_by(admission_id=admission_id)
        .order_by(
            WardTransfer.transferred_at.desc(),
            WardTransfer.id.desc(),
        )
        .first()
    )


# ============================================================================
# Ward management
# ============================================================================

def get_ward(ward_id: int) -> Ward:
    return _get_ward(ward_id)


def list_wards(
    clinic_id: int,
    ward_type: WardType | None = None,
) -> list[Ward]:
    _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    ensure_clinic_active(clinic_id)

    query = Ward.query.filter_by(
        clinic_id=clinic_id
    )

    if ward_type is not None:
        _validate_ward_type(ward_type)

        if not isinstance(ward_type, WardType):
            ward_type = WardType(ward_type)

        query = query.filter_by(
            ward_type=ward_type
        )

    return (
        query
        .order_by(Ward.name.asc())
        .all()
    )


@transactional
def create_ward(
    clinic_id: int,
    name: str,
    ward_type: WardType = WardType.GENERAL,
    capacity: int = 0,
) -> Ward:
    _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    ensure_clinic_active(clinic_id)

    name = _normalize_text(name)

    if not name:
        raise ValidationError(
            "Ward name is required"
        )

    if len(name) > 150:
        raise ValidationError(
            "Ward name cannot exceed 150 characters"
        )

    _validate_ward_type(ward_type)
    _validate_ward_capacity_value(capacity)

    if not isinstance(ward_type, WardType):
        ward_type = WardType(ward_type)

    existing = (
        Ward.query
        .filter_by(
            clinic_id=clinic_id,
            name=name,
        )
        .first()
    )

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
        action=AuditAction.CREATE,
        entity_type="Ward",
        entity_id=ward.id,
        description=(
            f"Ward '{ward.name}' created"
        ),
        new_value={
            "clinic_id": clinic_id,
            "name": ward.name,
            "ward_type": ward.ward_type.value,
            "capacity": ward.capacity,
        },
    )

    return ward


@transactional
def update_ward(
    ward_id: int,
    **fields,
) -> Ward:
    ward = _get_ward(
        ward_id,
        lock=True,
    )

    allowed_fields = {
        "name",
        "ward_type",
        "capacity",
    }

    unknown = set(fields) - allowed_fields

    if unknown:
        raise ValidationError(
            "Unknown ward field(s): "
            + ", ".join(sorted(unknown))
        )

    old_value = {}
    new_value = {}

    if "name" in fields:
        name = _normalize_text(
            fields["name"]
        )

        if not name:
            raise ValidationError(
                "Ward name is required"
            )

        if len(name) > 150:
            raise ValidationError(
                "Ward name cannot exceed 150 characters"
            )

        if name != ward.name:
            duplicate = (
                Ward.query
                .filter(
                    Ward.clinic_id == ward.clinic_id,
                    Ward.name == name,
                    Ward.id != ward.id,
                )
                .first()
            )

            if duplicate is not None:
                raise ConflictError(
                    f"Ward '{name}' already exists "
                    f"in clinic {ward.clinic_id}"
                )

            old_value["name"] = ward.name
            new_value["name"] = name

            ward.name = name

    if "ward_type" in fields:
        ward_type = fields["ward_type"]

        _validate_ward_type(ward_type)

        if not isinstance(ward_type, WardType):
            ward_type = WardType(ward_type)

        if ward_type != ward.ward_type:
            old_value["ward_type"] = (
                ward.ward_type.value
            )
            new_value["ward_type"] = (
                ward_type.value
            )

            ward.ward_type = ward_type

    if "capacity" in fields:
        capacity = fields["capacity"]

        _validate_new_capacity(
            ward=ward,
            new_capacity=capacity,
        )

        if capacity != ward.capacity:
            old_value["capacity"] = ward.capacity
            new_value["capacity"] = capacity

            ward.capacity = capacity

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Ward",
            entity_id=ward.id,
            description=(
                f"Ward '{ward.name}' updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return ward


def get_ward_occupancy(
    ward_id: int,
) -> dict:
    ward = _get_ward(ward_id)

    total_beds = len(ward.beds)

    available = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.AVAILABLE
    )

    occupied = sum(
        1
        for bed in ward.beds
        if bed.status == BedStatus.OCCUPIED
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
        "capacity": ward.capacity,
        "total_beds": total_beds,
        "available": available,
        "occupied": occupied,
        "reserved": reserved,
        "maintenance": maintenance,
        "occupancy_rate": (
            round(
                (occupied / total_beds) * 100,
                2,
            )
            if total_beds
            else 0
        ),
    }


# ============================================================================
# Bed management
# ============================================================================

def get_bed(bed_id: int) -> Bed:
    return _get_bed(bed_id)


def list_beds(
    ward_id: int,
    status: BedStatus | None = None,
) -> list[Bed]:
    ward = _get_ward(ward_id)

    query = Bed.query.filter_by(
        ward_id=ward.id
    )

    if status is not None:
        if not isinstance(status, BedStatus):
            try:
                status = BedStatus(status)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    f"Invalid bed status '{status}'"
                ) from exc

        query = query.filter_by(
            status=status
        )

    return (
        query
        .order_by(Bed.bed_number.asc())
        .all()
    )


@transactional
def add_bed(
    ward_id: int,
    bed_number: str,
) -> Bed:
    ward = _get_ward(
        ward_id,
        lock=True,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    bed_number = _validate_bed_number(
        bed_number
    )

    existing = (
        Bed.query
        .filter_by(
            ward_id=ward.id,
            bed_number=bed_number,
        )
        .first()
    )

    if existing is not None:
        raise ConflictError(
            f"Bed '{bed_number}' already exists "
            f"in ward {ward.id}"
        )

    configured_beds = _get_configured_bed_count(
        ward.id
    )

    if configured_beds >= ward.capacity:
        raise ConflictError(
            f"Ward {ward.id} has reached its "
            f"configured capacity of {ward.capacity}"
        )

    bed = Bed(
        ward_id=ward.id,
        bed_number=bed_number,
        status=BedStatus.AVAILABLE,
    )

    db.session.add(bed)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed '{bed.bed_number}' added "
            f"to ward {ward.id}"
        ),
        new_value={
            "ward_id": ward.id,
            "bed_number": bed.bed_number,
            "status": bed.status.value,
        },
    )

    return bed


@transactional
def set_bed_maintenance(
    bed_id: int,
    under_maintenance: bool,
) -> Bed:
    bed = _get_bed(
        bed_id,
        lock=True,
    )

    ward = bed.ward

    if ward is None:
        raise ValidationError(
            f"Bed {bed.id} has no associated ward"
        )

    ensure_clinic_active(
        ward.clinic_id
    )

    if not isinstance(
        under_maintenance,
        bool,
    ):
        raise ValidationError(
            "under_maintenance must be a boolean"
        )

    old_status = bed.status

    if under_maintenance:
        if bed.status == BedStatus.MAINTENANCE:
            return bed

        if bed.status == BedStatus.OCCUPIED:
            raise ConflictError(
                f"Bed {bed.id} is occupied and "
                f"cannot be placed into maintenance"
            )

        if bed.status == BedStatus.RESERVED:
            raise ConflictError(
                f"Bed {bed.id} is reserved and "
                f"cannot be placed into maintenance"
            )

        bed.status = BedStatus.MAINTENANCE

    else:
        if bed.status == BedStatus.AVAILABLE:
            return bed

        if bed.status != BedStatus.MAINTENANCE:
            raise ConflictError(
                f"Bed {bed.id} is "
                f"'{bed.status.value}' and cannot "
                f"be restored from maintenance"
            )

        bed.status = BedStatus.AVAILABLE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed status changed to "
            f"'{bed.status.value}'"
        ),
        old_value={
            "status": old_status.value
        },
        new_value={
            "status": bed.status.value
        },
    )

    return bed


# ============================================================================
# Bed reservations
# ============================================================================

def get_bed_reservation(
    reservation_id: int,
) -> BedReservation:
    return _get_reservation(
        reservation_id
    )


def list_bed_reservations(
    clinic_id: int,
    status: ReservationStatus | None = None,
    patient_id: int | None = None,
    bed_id: int | None = None,
) -> list[BedReservation]:
    _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    ensure_clinic_active(clinic_id)

    query = (
        BedReservation.query
        .join(Bed)
        .join(Ward)
        .filter(
            Ward.clinic_id == clinic_id
        )
    )

    if status is not None:
        if not isinstance(
            status,
            ReservationStatus,
        ):
            try:
                status = ReservationStatus(status)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    f"Invalid reservation status "
                    f"'{status}'"
                ) from exc

        query = query.filter(
            BedReservation.status == status
        )

    if patient_id is not None:
        _validate_positive_id(
            patient_id,
            "patient_id",
        )

        query = query.filter(
            BedReservation.patient_id
            == patient_id
        )

    if bed_id is not None:
        _validate_positive_id(
            bed_id,
            "bed_id",
        )

        query = query.filter(
            BedReservation.bed_id == bed_id
        )

    return (
        query
        .order_by(
            BedReservation.reserved_at.desc()
        )
        .all()
    )


def get_active_bed_reservation_for_patient(
    patient_id: int,
) -> BedReservation | None:
    patient = _get_patient(patient_id)

    return (
        BedReservation.query
        .filter(
            BedReservation.patient_id == patient.id,
            BedReservation.status
            == ReservationStatus.PENDING,
        )
        .order_by(
            BedReservation.reserved_at.desc()
        )
        .first()
    )


def get_active_bed_reservation_for_bed(
    bed_id: int,
) -> BedReservation | None:
    bed = _get_bed(bed_id)

    return _get_active_reservation_for_bed(
        bed.id
    )


@transactional
def reserve_bed(
    *,
    patient_id: int,
    bed_id: int,
    reserved_by_id: int,
    reason: str | None = None,
    expires_at: datetime | None = None,
) -> BedReservation:
    """
    Reserve an available bed for a patient.

    Lifecycle:

        Bed:         AVAILABLE -> RESERVED
        Reservation: PENDING

    Locks the patient first and the bed second so concurrent
    requests cannot create two active reservations/admissions
    for the same patient or reserve the same bed twice.
    """

    reason = _validate_reason(reason)

    if expires_at is not None:
        if expires_at <= _utcnow():
            raise ValidationError(
                "expires_at must be in the future"
            )

    patient = _get_patient(
        patient_id,
        lock=True,
    )

    bed = _get_bed(
        bed_id,
        lock=True,
    )

    ward = _validate_bed_for_clinic(
        bed=bed,
        clinic_id=bed.ward.clinic_id,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    _validate_patient_for_clinic(
        patient=patient,
        clinic_id=ward.clinic_id,
    )

    _validate_staff_for_clinic(
        staff_id=reserved_by_id,
        clinic_id=ward.clinic_id,
    )

    active_admission = (
        _get_active_admission_for_patient_locked(
            patient.id
        )
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"active admission {active_admission.id}"
        )

    active_reservation = (
        _get_active_reservation_for_patient_locked(
            patient.id
        )
    )

    if active_reservation is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"active bed reservation "
            f"{active_reservation.id}"
        )

    if bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed.id} is "
            f"'{bed.status.value}', not available"
        )

    existing_bed_reservation = (
        _get_active_reservation_for_bed(
            bed.id
        )
    )

    if existing_bed_reservation is not None:
        raise ConflictError(
            f"Bed {bed.id} is already reserved "
            f"by reservation "
            f"{existing_bed_reservation.id}"
        )

    reservation = BedReservation(
        patient_id=patient.id,
        bed_id=bed.id,
        reserved_by_id=reserved_by_id,
        status=ReservationStatus.PENDING,
        reason=reason,
        reserved_at=_utcnow(),
        expires_at=expires_at,
    )

    db.session.add(reservation)

    bed.status = BedStatus.RESERVED

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="BedReservation",
        entity_id=reservation.id,
        description=(
            f"Bed {bed.id} reserved for "
            f"patient {patient.id}"
        ),
        new_value={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "reserved_by_id": reserved_by_id,
            "status": reservation.status.value,
            "reason": reason,
            "expires_at": (
                expires_at.isoformat()
                if expires_at
                else None
            ),
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed {bed.id} marked as reserved"
        ),
        old_value={
            "status": BedStatus.AVAILABLE.value
        },
        new_value={
            "status": BedStatus.RESERVED.value
        },
    )

    return reservation


@transactional
def cancel_bed_reservation(
    reservation_id: int,
    reason: str | None = None,
) -> BedReservation:
    """
    Cancel a pending reservation.

    Lifecycle:

        Reservation: PENDING -> CANCELLED
        Bed:         RESERVED -> AVAILABLE
    """

    reason = _validate_reason(reason)

    reservation = _get_reservation(
        reservation_id,
        lock=True,
    )

    _assert_reservation_pending(
        reservation
    )

    bed = _get_bed(
        reservation.bed_id,
        lock=True,
    )

    ward = _validate_bed_for_clinic(
        bed=bed,
        clinic_id=bed.ward.clinic_id,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    old_status = reservation.status

    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = _utcnow()

    if reason:
        reservation.reason = reason

    if bed.status == BedStatus.RESERVED:
        bed.status = BedStatus.AVAILABLE

    elif bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed.id} is "
            f"'{bed.status.value}' while "
            f"cancelling reservation "
            f"{reservation.id}"
        )

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="BedReservation",
        entity_id=reservation.id,
        description=(
            f"Bed reservation {reservation.id} "
            f"cancelled"
        ),
        old_value={
            "status": old_status.value
        },
        new_value={
            "status": reservation.status.value,
            "reason": reservation.reason,
            "cancelled_at": (
                reservation.cancelled_at.isoformat()
                if reservation.cancelled_at
                else None
            ),
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed {bed.id} released after "
            f"reservation cancellation"
        ),
        old_value={
            "status": BedStatus.RESERVED.value
        },
        new_value={
            "status": bed.status.value
        },
    )

    return reservation


@transactional
def expire_bed_reservation(
    reservation_id: int,
) -> BedReservation:
    """
    Expire a pending reservation.

    This is intended to be called by a scheduled job,
    or manually when a reservation has passed expires_at.

    Lifecycle:

        Reservation: PENDING -> EXPIRED
        Bed:         RESERVED -> AVAILABLE
    """

    reservation = _get_reservation(
        reservation_id,
        lock=True,
    )

    _assert_reservation_pending(
        reservation
    )

    if (
        reservation.expires_at is None
    ):
        raise ValidationError(
            f"Reservation {reservation.id} "
            f"does not have an expiry time"
        )

    now = _utcnow().replace(tzinfo=None)

    if reservation.expires_at > now:
        raise ConflictError(
            f"Reservation {reservation.id} "
            f"has not expired yet"
        )

    bed = _get_bed(
        reservation.bed_id,
        lock=True,
    )

    ward = _validate_bed_for_clinic(
        bed=bed,
        clinic_id=bed.ward.clinic_id,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    old_status = reservation.status

    reservation.status = ReservationStatus.EXPIRED

    if bed.status == BedStatus.RESERVED:
        bed.status = BedStatus.AVAILABLE

    elif bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed.id} is "
            f"'{bed.status.value}' while "
            f"expiring reservation "
            f"{reservation.id}"
        )

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="BedReservation",
        entity_id=reservation.id,
        description=(
            f"Bed reservation {reservation.id} "
            f"expired"
        ),
        old_value={
            "status": old_status.value
        },
        new_value={
            "status": reservation.status.value
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed {bed.id} released after "
            f"reservation expiry"
        ),
        old_value={
            "status": BedStatus.RESERVED.value
        },
        new_value={
            "status": bed.status.value
        },
    )

    return reservation


@transactional
def expire_due_bed_reservations(
    *,
    clinic_id: int | None = None,
) -> list[BedReservation]:
    """
    Expire all pending reservations whose expiry time
    has passed.

    This is suitable for a scheduled/background task.
    """

    now = _utcnow()

    query = (
        BedReservation.query
        .filter(
            BedReservation.status
            == ReservationStatus.PENDING,
            BedReservation.expires_at.isnot(None),
            BedReservation.expires_at <= now,
        )
    )

    if clinic_id is not None:
        _validate_positive_id(
            clinic_id,
            "clinic_id",
        )

        ensure_clinic_active(
            clinic_id
        )

        query = (
            query
            .join(Bed)
            .join(Ward)
            .filter(
                Ward.clinic_id == clinic_id
            )
        )

    reservations = (
        query
        .order_by(
            BedReservation.expires_at.asc()
        )
        .with_for_update()
        .all()
    )

    expired = []

    for reservation in reservations:
        bed = _get_bed(
            reservation.bed_id,
            lock=True,
        )

        if reservation.status != ReservationStatus.PENDING:
            continue

        reservation.status = ReservationStatus.EXPIRED

        if bed.status == BedStatus.RESERVED:
            bed.status = BedStatus.AVAILABLE

        elif bed.status != BedStatus.AVAILABLE:
            raise ConflictError(
                f"Bed {bed.id} is "
                f"'{bed.status.value}' while "
                f"expiring reservation "
                f"{reservation.id}"
            )

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="BedReservation",
            entity_id=reservation.id,
            description=(
                f"Bed reservation {reservation.id} "
                f"expired automatically"
            ),
            old_value={
                "status": ReservationStatus.PENDING.value
            },
            new_value={
                "status": ReservationStatus.EXPIRED.value
            },
        )

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Bed",
            entity_id=bed.id,
            description=(
                f"Bed {bed.id} released after "
                f"automatic reservation expiry"
            ),
            old_value={
                "status": BedStatus.RESERVED.value
            },
            new_value={
                "status": BedStatus.AVAILABLE.value
            },
        )

        expired.append(reservation)

    return expired


# ============================================================================
# Admissions
# ============================================================================

def get_admission(
    admission_id: int,
) -> Admission:
    return _get_admission(
        admission_id
    )


def get_active_admission_for_patient(
    patient_id: int,
) -> Admission | None:
    _get_patient(patient_id)

    return (
        Admission.query
        .filter(
            Admission.patient_id == patient_id,
            Admission.status
            == AdmissionStatus.ADMITTED,
        )
        .order_by(
            Admission.admitted_at.desc()
        )
        .first()
    )


def list_admissions_for_patient(
    patient_id: int,
) -> list[Admission]:
    _get_patient(patient_id)

    return (
        Admission.query
        .filter_by(
            patient_id=patient_id
        )
        .order_by(
            Admission.admitted_at.desc()
        )
        .all()
    )


def get_current_bed(
    patient_id: int,
) -> Bed | None:
    admission = get_active_admission_for_patient(
        patient_id
    )

    if admission is None:
        return None

    return admission.bed


@transactional
def admit_patient(
    *,
    patient_id: int,
    bed_id: int,
    admitted_by_id: int,
    reason: str | None = None,
) -> Admission:
    """
    Direct admission for walk-ins/emergency cases.

    Reservation-aware behavior:
    - A patient with an active reservation cannot be
      directly admitted through this function.
    - Reserved beds cannot be directly admitted into.
    - Use admit_patient_from_reservation() to fulfil
      a reservation.

    Lifecycle:

        Bed:       AVAILABLE -> OCCUPIED
        Admission: ADMITTED
    """

    reason = _validate_reason(reason)

    # Lock patient first to prevent concurrent admission
    # and reservation races.
    patient = _get_patient(
        patient_id,
        lock=True,
    )

    active_admission = (
        _get_active_admission_for_patient_locked(
            patient.id
        )
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"active admission {active_admission.id}"
        )

    active_reservation = (
        _get_active_reservation_for_patient_locked(
            patient.id
        )
    )

    if active_reservation is not None:
        raise ConflictError(
            f"Patient {patient.id} has active "
            f"bed reservation "
            f"{active_reservation.id}; "
            f"use admit_patient_from_reservation()"
        )

    bed = _get_bed(
        bed_id,
        lock=True,
    )

    ward = _validate_bed_for_clinic(
        bed=bed,
        clinic_id=bed.ward.clinic_id,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    _validate_patient_for_clinic(
        patient=patient,
        clinic_id=ward.clinic_id,
    )

    _validate_staff_for_clinic(
        staff_id=admitted_by_id,
        clinic_id=ward.clinic_id,
    )

    if bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed.id} is "
            f"'{bed.status.value}', not available"
        )

    admission = Admission(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=admitted_by_id,
        status=AdmissionStatus.ADMITTED,
        reason=reason,
        admitted_at=_utcnow(),
    )

    db.session.add(admission)

    bed.status = BedStatus.OCCUPIED

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            f"Patient {patient.id} admitted "
            f"to bed {bed.id}"
        ),
        new_value={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "admitted_by_id": admitted_by_id,
            "status": admission.status.value,
            "reason": reason,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed {bed.id} occupied by "
            f"patient {patient.id}"
        ),
        old_value={
            "status": BedStatus.AVAILABLE.value
        },
        new_value={
            "status": BedStatus.OCCUPIED.value
        },
    )

    return admission


@transactional
def admit_patient_from_reservation(
    *,
    reservation_id: int,
    admitted_by_id: int,
    reason: str | None = None,
) -> Admission:
    """
    Fulfil a pending bed reservation by admitting
    the reserved patient into the reserved bed.

    Lifecycle:

        Reservation: PENDING -> FULFILLED
        Bed:         RESERVED -> OCCUPIED
        Admission:   ADMITTED
    """

    reason = _validate_reason(reason)

    reservation = _get_reservation(
        reservation_id,
        lock=True,
    )

    _assert_reservation_pending(
        reservation
    )

    # Lock patient before checking active admission.
    patient = _get_patient(
        reservation.patient_id,
        lock=True,
    )

    active_admission = (
        _get_active_admission_for_patient_locked(
            patient.id
        )
    )

    if active_admission is not None:
        raise ConflictError(
            f"Patient {patient.id} already has "
            f"active admission {active_admission.id}"
        )

    bed = _get_bed(
        reservation.bed_id,
        lock=True,
    )

    ward = _validate_bed_for_clinic(
        bed=bed,
        clinic_id=bed.ward.clinic_id,
    )

    ensure_clinic_active(
        ward.clinic_id
    )

    _validate_patient_for_clinic(
        patient=patient,
        clinic_id=ward.clinic_id,
    )

    _validate_staff_for_clinic(
        staff_id=admitted_by_id,
        clinic_id=ward.clinic_id,
    )

    if bed.status != BedStatus.RESERVED:
        raise ConflictError(
            f"Reserved bed {bed.id} is "
            f"'{bed.status.value}', not reserved"
        )

    # Ensure the reservation is still the active reservation
    # attached to this bed.
    active_bed_reservation = (
        _get_active_reservation_for_bed(
            bed.id
        )
    )

    if (
        active_bed_reservation is not None
        and active_bed_reservation.id
        != reservation.id
    ):
        raise ConflictError(
            f"Bed {bed.id} has another active "
            f"reservation "
            f"{active_bed_reservation.id}"
        )

    admission = Admission(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=admitted_by_id,
        reservation_id=reservation.id,
        status=AdmissionStatus.ADMITTED,
        reason=(
            reason
            if reason is not None
            else reservation.reason
        ),
        admitted_at=_utcnow(),
    )

    db.session.add(admission)

    reservation.status = ReservationStatus.FULFILLED
    reservation.fulfilled_at = _utcnow()

    bed.status = BedStatus.OCCUPIED

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="BedReservation",
        entity_id=reservation.id,
        description=(
            f"Bed reservation {reservation.id} "
            f"fulfilled by admission "
            f"{admission.id}"
        ),
        old_value={
            "status": ReservationStatus.PENDING.value
        },
        new_value={
            "status": ReservationStatus.FULFILLED.value,
            "fulfilled_at": (
                reservation.fulfilled_at.isoformat()
                if reservation.fulfilled_at
                else None
            ),
            "admission_id": admission.id,
        },
    )

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            f"Patient {patient.id} admitted "
            f"from reservation "
            f"{reservation.id}"
        ),
        new_value={
            "patient_id": patient.id,
            "bed_id": bed.id,
            "admitted_by_id": admitted_by_id,
            "reservation_id": reservation.id,
            "status": admission.status.value,
            "reason": admission.reason,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Reserved bed {bed.id} occupied "
            f"by patient {patient.id}"
        ),
        old_value={
            "status": BedStatus.RESERVED.value
        },
        new_value={
            "status": BedStatus.OCCUPIED.value
        },
    )

    return admission


# Optional explicit alias for callers that prefer
# the reservation terminology.
fulfill_bed_reservation = admit_patient_from_reservation


# ============================================================================
# Admissions / transfers
# ============================================================================

@transactional
def transfer_bed(
    *,
    admission_id: int,
    to_bed_id: int,
    reason: str | None = None,
) -> WardTransfer:
    """
    Transfer an actively admitted patient to another
    available bed.

    Lifecycle:

        Current bed: AVAILABLE
        Target bed:  AVAILABLE -> OCCUPIED

    The admission remains ADMITTED.

    AdmissionStatus.TRANSFERRED is intentionally not used
    here because this is an internal bed transfer within
    the same active admission.
    """

    reason = _validate_reason(reason)

    admission = _get_admission(
        admission_id,
        lock=True,
    )

    _assert_admission_active(
        admission
    )

    from_bed = _get_bed(
        admission.bed_id,
        lock=True,
    )

    to_bed = _get_bed(
        to_bed_id,
        lock=True,
    )

    if from_bed.id == to_bed.id:
        raise ValidationError(
            "Source and destination beds must be different"
        )

    clinic_id = _get_admission_clinic_id(
        admission
    )

    ensure_clinic_active(
        clinic_id
    )

    _validate_bed_for_clinic(
        bed=from_bed,
        clinic_id=clinic_id,
    )

    _validate_bed_for_clinic(
        bed=to_bed,
        clinic_id=clinic_id,
    )

    if from_bed.status != BedStatus.OCCUPIED:
        raise ConflictError(
            f"Current bed {from_bed.id} is "
            f"'{from_bed.status.value}', not occupied"
        )

    if to_bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Destination bed {to_bed.id} is "
            f"'{to_bed.status.value}', not available"
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
        action=AuditAction.CREATE,
        entity_type="WardTransfer",
        entity_id=transfer.id,
        description=(
            f"Admission {admission.id} transferred "
            f"from bed {from_bed.id} "
            f"to bed {to_bed.id}"
        ),
        new_value={
            "admission_id": admission.id,
            "from_bed_id": from_bed.id,
            "to_bed_id": to_bed.id,
            "reason": reason,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=from_bed.id,
        description=(
            f"Bed {from_bed.id} released after "
            f"patient transfer"
        ),
        old_value={
            "status": BedStatus.OCCUPIED.value
        },
        new_value={
            "status": BedStatus.AVAILABLE.value
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=to_bed.id,
        description=(
            f"Bed {to_bed.id} occupied after "
            f"patient transfer"
        ),
        old_value={
            "status": BedStatus.AVAILABLE.value
        },
        new_value={
            "status": BedStatus.OCCUPIED.value
        },
    )

    return transfer


# ============================================================================
# Discharge
# ============================================================================

@transactional
def discharge_patient(
    *,
    admission_id: int,
    reason: str | None = None,
) -> Admission:
    """
    Discharge an actively admitted patient.

    Lifecycle:

        Admission: ADMITTED -> DISCHARGED
        Bed:       OCCUPIED -> AVAILABLE
    """

    reason = _validate_reason(reason)

    admission = _get_admission(
        admission_id,
        lock=True,
    )

    _assert_admission_active(
        admission
    )

    bed = _get_bed(
        admission.bed_id,
        lock=True,
    )

    clinic_id = _get_admission_clinic_id(
        admission
    )

    ensure_clinic_active(
        clinic_id
    )

    if bed.status != BedStatus.OCCUPIED:
        raise ConflictError(
            f"Admission {admission.id} points to "
            f"bed {bed.id}, but the bed is "
            f"'{bed.status.value}'"
        )

    old_status = admission.status

    admission.status = AdmissionStatus.DISCHARGED
    admission.discharged_at = _utcnow()

    if reason is not None:
        admission.reason = reason

    bed.status = BedStatus.AVAILABLE

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            f"Admission {admission.id} discharged"
        ),
        old_value={
            "status": old_status.value
        },
        new_value={
            "status": admission.status.value,
            "discharged_at": (
                admission.discharged_at.isoformat()
                if admission.discharged_at
                else None
            ),
            "reason": admission.reason,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed {bed.id} released after "
            f"patient discharge"
        ),
        old_value={
            "status": BedStatus.OCCUPIED.value
        },
        new_value={
            "status": BedStatus.AVAILABLE.value
        },
    )

    return admission