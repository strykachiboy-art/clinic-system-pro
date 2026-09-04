from datetime import datetime, timezone

from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.ward_enums import (
    BedStatus,
    AdmissionStatus,
)
from app.modules.ward.models.ward_model import (
    Ward,
    Bed,
    Admission,
    WardTransfer,
)
from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.patient.models.patient_model import Patient
from app.modules.staff.models.staff_model import Staff


def _utcnow():
    return datetime.now(timezone.utc)


# =====================================================================
# Internal helpers
# =====================================================================

def _get_ward(ward_id: int, *, lock: bool = False) -> Ward:
    query = Ward.query.filter_by(id=ward_id)

    if lock:
        query = query.with_for_update()

    ward = query.first()

    if ward is None:
        raise NotFoundError(f"Ward {ward_id} not found")

    return ward


def _get_bed(bed_id: int, *, lock: bool = False) -> Bed:
    query = Bed.query.filter_by(id=bed_id)

    if lock:
        query = query.with_for_update()

    bed = query.first()

    if bed is None:
        raise NotFoundError(f"Bed {bed_id} not found")

    return bed


def _get_admission(admission_id: int, *, lock: bool = False) -> Admission:
    query = Admission.query.filter_by(id=admission_id)

    if lock:
        query = query.with_for_update()

    admission = query.first()

    if admission is None:
        raise NotFoundError(f"Admission {admission_id} not found")

    return admission


def _get_patient(patient_id: int) -> Patient:
    patient = db.session.get(Patient, patient_id)

    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found")

    return patient


def _get_staff(staff_id: int) -> Staff:
    staff = db.session.get(Staff, staff_id)

    if staff is None:
        raise NotFoundError(f"Staff {staff_id} not found")

    return staff


def _validate_ward_belongs_to_clinic(
    ward: Ward,
    clinic_id: int,
) -> None:
    if ward.clinic_id != clinic_id:
        raise ValidationError(
            f"Ward {ward.id} does not belong to clinic {clinic_id}"
        )


def _validate_bed_clinic(
    bed: Bed,
    clinic_id: int,
) -> None:
    if bed.ward is None:
        raise ValidationError(
            f"Bed {bed.id} is not associated with a ward"
        )

    if bed.ward.clinic_id != clinic_id:
        raise ValidationError(
            f"Bed {bed.id} does not belong to clinic {clinic_id}"
        )


def _validate_patient_clinic(
    patient: Patient,
    clinic_id: int,
) -> None:
    if patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Patient {patient.id} does not belong to clinic {clinic_id}"
        )


def _validate_staff_clinic(
    staff: Staff,
    clinic_id: int,
) -> None:
    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Staff {staff.id} does not belong to clinic {clinic_id}"
        )


def _get_bed_clinic_id(bed: Bed) -> int:
    if bed.ward is None:
        raise ValidationError(
            f"Bed {bed.id} is not associated with a ward"
        )

    return bed.ward.clinic_id


def _validate_ward_capacity(ward: Ward) -> None:
    """
    Ensures the number of configured beds does not exceed ward capacity.

    A capacity of 0 is treated as an explicitly configured zero-capacity
    ward, so no beds can be added until the ward capacity is increased.
    """
    current_bed_count = Bed.query.filter_by(
        ward_id=ward.id
    ).count()

    if current_bed_count >= ward.capacity:
        raise ConflictError(
            f"Ward {ward.id} has reached its configured capacity "
            f"of {ward.capacity} beds"
        )


def _get_latest_transfer(admission_id: int) -> WardTransfer | None:
    return (
        WardTransfer.query
        .filter_by(admission_id=admission_id)
        .order_by(
            WardTransfer.transferred_at.desc(),
            WardTransfer.id.desc(),
        )
        .first()
    )


def _assert_admission_active(admission: Admission) -> None:
    if admission.status != AdmissionStatus.ADMITTED:
        raise ConflictError(
            f"Admission {admission.id} is not active "
            f"('{admission.status.value}')"
        )


def _get_admission_clinic_id(admission: Admission) -> int:
    current_bed = get_current_bed(admission)

    return _get_bed_clinic_id(current_bed)


# =====================================================================
# Wards
# =====================================================================

def get_ward(ward_id: int) -> Ward:
    """
    Retrieve a ward regardless of clinic status.

    Historical records remain readable even when the clinic is
    inactive or suspended.
    """
    return _get_ward(ward_id)


def list_wards(clinic_id: int | None = None) -> list[Ward]:
    query = Ward.query

    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)

    return query.order_by(Ward.name.asc()).all()


@transactional
def create_ward(
    clinic_id: int,
    name: str,
    **fields,
) -> Ward:
    """
    Create a ward for an active clinic.
    """

    ensure_clinic_active(clinic_id)

    if not name or not name.strip():
        raise ValidationError("Ward name is required")

    name = name.strip()

    duplicate = Ward.query.filter_by(
        clinic_id=clinic_id,
        name=name,
    ).first()

    if duplicate:
        raise ConflictError(
            f"Ward '{name}' already exists in clinic {clinic_id}"
        )

    capacity = fields.get("capacity", 0)

    if capacity is None:
        capacity = 0

    if capacity < 0:
        raise ValidationError(
            "Ward capacity cannot be negative"
        )

    fields["capacity"] = capacity

    ward = Ward(
        clinic_id=clinic_id,
        name=name,
        **fields,
    )

    db.session.add(ward)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Ward",
        entity_id=ward.id,
        description=f"Ward '{ward.name}' created",
        new_value={
            "clinic_id": ward.clinic_id,
            "name": ward.name,
            "ward_type": ward.ward_type.value,
            "capacity": ward.capacity,
        },
    )

    return ward


def get_ward_occupancy(ward_id: int) -> dict:
    """
    Return ward occupancy information.

    This is a read operation and therefore works even when the
    clinic is inactive or suspended.
    """

    ward = get_ward(ward_id)

    beds = ward.beds

    occupied = sum(
        1 for bed in beds
        if bed.status == BedStatus.OCCUPIED
    )

    available = sum(
        1 for bed in beds
        if bed.status == BedStatus.AVAILABLE
    )

    reserved = sum(
        1 for bed in beds
        if bed.status == BedStatus.RESERVED
    )

    maintenance = sum(
        1 for bed in beds
        if bed.status == BedStatus.MAINTENANCE
    )

    return {
        "ward_id": ward.id,
        "clinic_id": ward.clinic_id,
        "ward_name": ward.name,
        "capacity": ward.capacity,
        "total_beds": len(beds),
        "occupied": occupied,
        "available": available,
        "reserved": reserved,
        "maintenance": maintenance,
    }


# =====================================================================
# Beds
# =====================================================================

def get_bed(bed_id: int) -> Bed:
    """
    Retrieve a bed regardless of clinic status.
    """
    return _get_bed(bed_id)


def list_beds(
    ward_id: int,
    status: BedStatus | None = None,
) -> list[Bed]:

    get_ward(ward_id)

    query = Bed.query.filter_by(
        ward_id=ward_id
    )

    if status is not None:
        query = query.filter_by(status=status)

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
    """
    Add a new available bed to an active clinic's ward.
    """

    ward = _get_ward(ward_id)

    ensure_clinic_active(ward.clinic_id)

    if not bed_number or not bed_number.strip():
        raise ValidationError("Bed number is required")

    bed_number = bed_number.strip()

    _validate_ward_capacity(ward)

    duplicate = Bed.query.filter_by(
        ward_id=ward_id,
        bed_number=bed_number,
    ).first()

    if duplicate:
        raise ConflictError(
            f"Bed '{bed_number}' already exists in ward {ward_id}"
        )

    bed = Bed(
        ward_id=ward_id,
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
            f"Bed '{bed.bed_number}' added to ward {ward_id}"
        ),
        new_value={
            "ward_id": ward_id,
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
    """
    Manually place a bed into or remove it from maintenance.

    Maintenance changes are only allowed for beds belonging to an
    active clinic.

    An occupied bed cannot be placed into maintenance.
    """

    bed = _get_bed(
        bed_id,
        lock=True,
    )

    clinic_id = _get_bed_clinic_id(bed)

    ensure_clinic_active(clinic_id)

    if bed.status == BedStatus.OCCUPIED:
        raise ConflictError(
            "Cannot change maintenance status on an occupied bed"
        )

    target_status = (
        BedStatus.MAINTENANCE
        if under_maintenance
        else BedStatus.AVAILABLE
    )

    if bed.status == target_status:
        return bed

    old_status = bed.status.value

    bed.status = target_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=(
            f"Bed marked "
            f"{'under maintenance' if under_maintenance else 'available'}"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": bed.status.value,
        },
    )

    return bed


# =====================================================================
# Admissions
# =====================================================================

def get_admission(admission_id: int) -> Admission:
    """
    Retrieve an admission regardless of admission/clinic status.
    """
    return _get_admission(admission_id)


def get_active_admission_for_patient(
    patient_id: int,
) -> Admission | None:
    return (
        Admission.query
        .filter(
            Admission.patient_id == patient_id,
            Admission.status == AdmissionStatus.ADMITTED,
        )
        .order_by(Admission.admitted_at.desc())
        .first()
    )


def list_admissions_for_patient(
    patient_id: int,
) -> list[Admission]:

    _get_patient(patient_id)

    return (
        Admission.query
        .filter_by(patient_id=patient_id)
        .order_by(
            Admission.admitted_at.desc(),
            Admission.id.desc(),
        )
        .all()
    )


@transactional
def admit_patient(
    patient_id: int,
    bed_id: int,
    admitted_by_id: int,
    reason: str | None = None,
) -> Admission:
    """
    Admit a patient into an available bed.

    The patient, bed/ward, and admitting staff must all belong to
    the same active clinic.
    """

    patient = _get_patient(patient_id)

    if get_active_admission_for_patient(patient_id):
        raise ConflictError(
            f"Patient {patient_id} already has an active admission"
        )

    bed = _get_bed(
        bed_id,
        lock=True,
    )

    clinic_id = _get_bed_clinic_id(bed)

    ensure_clinic_active(clinic_id)

    _validate_patient_clinic(
        patient,
        clinic_id,
    )

    admitted_by = _get_staff(admitted_by_id)

    _validate_staff_clinic(
        admitted_by,
        clinic_id,
    )

    if bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {bed_id} is '{bed.status.value}', "
            "not available"
        )

    if reason is not None:
        reason = reason.strip() or None

    bed.status = BedStatus.OCCUPIED

    now = _utcnow()

    admission = Admission(
        patient_id=patient_id,
        bed_id=bed_id,
        admitted_by_id=admitted_by_id,
        status=AdmissionStatus.ADMITTED,
        reason=reason,
        admitted_at=now,
    )

    db.session.add(admission)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            f"Patient {patient_id} admitted "
            f"to bed {bed_id}"
        ),
        new_value={
            "patient_id": patient_id,
            "bed_id": bed_id,
            "clinic_id": clinic_id,
            "admitted_by_id": admitted_by_id,
            "reason": reason,
        },
    )

    return admission


@transactional
def transfer_bed(
    admission_id: int,
    to_bed_id: int,
    reason: str | None = None,
) -> WardTransfer:
    """
    Transfer an active admission to another available bed.

    Admission.bed_id remains the original admitting bed.

    The current bed is determined from the latest WardTransfer,
    falling back to Admission.bed_id when no transfer exists.
    """

    admission = _get_admission(
        admission_id,
        lock=True,
    )

    _assert_admission_active(admission)

    current_bed = get_current_bed(admission)

    from_bed = _get_bed(
        current_bed.id,
        lock=True,
    )

    to_bed = _get_bed(
        to_bed_id,
        lock=True,
    )

    clinic_id = _get_bed_clinic_id(from_bed)

    ensure_clinic_active(clinic_id)

    _validate_bed_clinic(
        to_bed,
        clinic_id,
    )

    if to_bed.id == from_bed.id:
        raise ValidationError(
            "Cannot transfer to the same bed"
        )

    if to_bed.status != BedStatus.AVAILABLE:
        raise ConflictError(
            f"Bed {to_bed.id} is "
            f"'{to_bed.status.value}', not available"
        )

    if reason is not None:
        reason = reason.strip() or None

    from_bed.status = BedStatus.AVAILABLE
    to_bed.status = BedStatus.OCCUPIED

    transfer = WardTransfer(
        admission_id=admission.id,
        from_bed_id=from_bed.id,
        to_bed_id=to_bed.id,
        reason=reason,
        transferred_at=_utcnow(),
    )

    db.session.add(transfer)
    db.session.flush()

    # IMPORTANT:
    #
    # A transfer does NOT terminate the admission.
    #
    # The patient is still admitted, therefore the admission remains
    # ADMITTED. The WardTransfer record represents the movement.
    #
    # Do NOT set:
    #
    # admission.status = AdmissionStatus.TRANSFERRED
    #
    # because that would make active-admission lookups unreliable.

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            f"Patient transferred from bed "
            f"{from_bed.id} to bed {to_bed.id}"
            + (f": {reason}" if reason else "")
        ),
        old_value={
            "bed_id": from_bed.id,
        },
        new_value={
            "bed_id": to_bed.id,
        },
    )

    return transfer


def get_current_bed(admission: Admission) -> Bed:
    """
    Derive the current bed from transfer history.

    If no transfer exists, the original Admission.bed_id is the
    current bed.
    """

    latest_transfer = _get_latest_transfer(
        admission.id
    )

    if latest_transfer is not None:
        return latest_transfer.to_bed

    if admission.bed is None:
        raise ValidationError(
            f"Admission {admission.id} has no associated bed"
        )

    return admission.bed


@transactional
def discharge_patient(
    admission_id: int,
    reason: str | None = None,
) -> Admission:
    """
    Discharge an active patient and release the patient's current bed.
    """

    admission = _get_admission(
        admission_id,
        lock=True,
    )

    _assert_admission_active(admission)

    current_bed = get_current_bed(admission)

    current_bed = _get_bed(
        current_bed.id,
        lock=True,
    )

    clinic_id = _get_bed_clinic_id(current_bed)

    ensure_clinic_active(clinic_id)

    if current_bed.status != BedStatus.OCCUPIED:
        raise ConflictError(
            f"Current bed {current_bed.id} is "
            f"'{current_bed.status.value}', expected occupied"
        )

    if reason is not None:
        reason = reason.strip() or None

    old_status = admission.status.value

    current_bed.status = BedStatus.AVAILABLE

    admission.status = AdmissionStatus.DISCHARGED
    admission.discharged_at = _utcnow()

    if reason:
        existing_reason = admission.reason or ""

        admission.reason = (
            f"{existing_reason}\n"
            f"Discharge note: {reason}"
        ).strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Admission",
        entity_id=admission.id,
        description=(
            "Patient discharged"
            + (f": {reason}" if reason else "")
        ),
        old_value={
            "status": old_status,
            "bed_id": current_bed.id,
        },
        new_value={
            "status": admission.status.value,
            "bed_id": None,
        },
    )

    return admission