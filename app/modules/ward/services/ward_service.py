from datetime import datetime, timezone
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.ward_enums import BedStatus, AdmissionStatus
from app.modules.ward.models.ward_model import Ward, Bed, Admission, WardTransfer


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Wards
# ---------------------------------------------------------------------

def get_ward(ward_id: int) -> Ward:
    ward = Ward.query.get(ward_id)
    if ward is None:
        raise NotFoundError(f"Ward {ward_id} not found")
    return ward


def list_wards(clinic_id: int | None = None) -> list[Ward]:
    query = Ward.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    return query.order_by(Ward.name).all()


@transactional
def create_ward(clinic_id: int, name: str, **fields) -> Ward:
    if not name or not name.strip():
        raise ValidationError("Ward name is required")

    ward = Ward(clinic_id=clinic_id, name=name.strip(), **fields)
    db.session.add(ward)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Ward",
        entity_id=ward.id,
        description=f"Ward '{ward.name}' created",
        new_value={"name": ward.name, "ward_type": ward.ward_type.value},
    )
    return ward


def get_ward_occupancy(ward_id: int) -> dict:
    ward = get_ward(ward_id)
    beds = ward.beds
    occupied = sum(1 for b in beds if b.status == BedStatus.OCCUPIED)
    available = sum(1 for b in beds if b.status == BedStatus.AVAILABLE)
    return {
        "ward_id": ward.id,
        "total_beds": len(beds),
        "occupied": occupied,
        "available": available,
        "reserved": sum(1 for b in beds if b.status == BedStatus.RESERVED),
        "maintenance": sum(1 for b in beds if b.status == BedStatus.MAINTENANCE),
    }


# ---------------------------------------------------------------------
# Beds
# ---------------------------------------------------------------------

def get_bed(bed_id: int) -> Bed:
    bed = Bed.query.get(bed_id)
    if bed is None:
        raise NotFoundError(f"Bed {bed_id} not found")
    return bed


def list_beds(ward_id: int, status: BedStatus | None = None) -> list[Bed]:
    get_ward(ward_id)
    query = Bed.query.filter_by(ward_id=ward_id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(Bed.bed_number).all()


@transactional
def add_bed(ward_id: int, bed_number: str) -> Bed:
    get_ward(ward_id)

    if not bed_number or not bed_number.strip():
        raise ValidationError("Bed number is required")

    duplicate = Bed.query.filter_by(ward_id=ward_id, bed_number=bed_number.strip()).first()
    if duplicate:
        raise ConflictError(f"Bed '{bed_number}' already exists in this ward")

    bed = Bed(ward_id=ward_id, bed_number=bed_number.strip(), status=BedStatus.AVAILABLE)
    db.session.add(bed)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Bed",
        entity_id=bed.id,
        description=f"Bed '{bed.bed_number}' added to ward {ward_id}",
    )
    return bed


@transactional
def set_bed_maintenance(bed_id: int, under_maintenance: bool) -> Bed:
    """
    Manual override for taking a bed in/out of service — the ONLY
    other place bed.status should ever be set is inside this service's
    admit/discharge/transfer functions, never directly by a caller.
    """
    bed = get_bed(bed_id)
    if bed.status == BedStatus.OCCUPIED:
        raise ConflictError("Cannot change maintenance status on an occupied bed")

    old_status = bed.status.value
    bed.status = BedStatus.MAINTENANCE if under_maintenance else BedStatus.AVAILABLE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Bed",
        entity_id=bed.id,
        description=f"Bed marked {'under maintenance' if under_maintenance else 'available'}",
        old_value={"status": old_status},
        new_value={"status": bed.status.value},
    )
    return bed


# ---------------------------------------------------------------------
# Admissions
# ---------------------------------------------------------------------

def get_admission(admission_id: int) -> Admission:
    admission = Admission.query.get(admission_id)
    if admission is None:
        raise NotFoundError(f"Admission {admission_id} not found")
    return admission


def get_active_admission_for_patient(patient_id: int) -> Admission | None:
    return Admission.query.filter_by(patient_id=patient_id, status=AdmissionStatus.ADMITTED).first()


def list_admissions_for_patient(patient_id: int) -> list[Admission]:
    return (
        Admission.query.filter_by(patient_id=patient_id)
        .order_by(Admission.admitted_at.desc())
        .all()
    )


@transactional
def admit_patient(patient_id: int, bed_id: int, admitted_by_id: int, reason: str | None = None) -> Admission:
    if get_active_admission_for_patient(patient_id):
        raise ConflictError(f"Patient {patient_id} already has an active admission")

    # Row lock — prevents two concurrent admissions claiming the same
    # bed between the status check and the write, same pattern as
    # pharmacy's FEFO batch allocation.
    bed = Bed.query.filter_by(id=bed_id).with_for_update().first()
    if bed is None:
        raise NotFoundError(f"Bed {bed_id} not found")
    if bed.status != BedStatus.AVAILABLE:
        raise ConflictError(f"Bed {bed_id} is '{bed.status.value}', not available")

    bed.status = BedStatus.OCCUPIED

    admission = Admission(
        patient_id=patient_id,
        bed_id=bed_id,
        admitted_by_id=admitted_by_id,
        status=AdmissionStatus.ADMITTED,
        reason=reason,
    )
    db.session.add(admission)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=f"Patient {patient_id} admitted to bed {bed_id}",
        new_value={"bed_id": bed_id, "reason": reason},
    )
    return admission


@transactional
def transfer_bed(admission_id: int, to_bed_id: int, reason: str | None = None) -> WardTransfer:
    """
    Moves an active admission to a different bed. The admission's
    `bed_id` column stays as the ORIGINAL admitting bed (matches your
    model — Admission.bed_id has no "current bed" semantics of its
    own); the CURRENT bed is derivable as the latest WardTransfer's
    to_bed, or the admission's original bed_id if no transfer exists
    yet. Worth exposing that derivation as get_current_bed() below
    rather than making every caller re-derive it themselves.
    """
    admission = get_admission(admission_id)
    if admission.status != AdmissionStatus.ADMITTED:
        raise ConflictError(f"Admission {admission_id} is not active ('{admission.status.value}')")

    from_bed = get_current_bed(admission)

    if to_bed_id == from_bed.id:
        raise ValidationError("Cannot transfer to the same bed")

    to_bed = Bed.query.filter_by(id=to_bed_id).with_for_update().first()
    if to_bed is None:
        raise NotFoundError(f"Bed {to_bed_id} not found")
    if to_bed.status != BedStatus.AVAILABLE:
        raise ConflictError(f"Bed {to_bed_id} is '{to_bed.status.value}', not available")

    from_bed.status = BedStatus.AVAILABLE
    to_bed.status = BedStatus.OCCUPIED
    admission.status = AdmissionStatus.TRANSFERRED  # marks that a transfer occurred; see note below
    admission.status = AdmissionStatus.ADMITTED

    transfer = WardTransfer(
        admission_id=admission.id,
        from_bed_id=from_bed.id,
        to_bed_id=to_bed_id,
        reason=reason,
    )
    db.session.add(transfer)
    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Admission",
        entity_id=admission.id,
        description=f"Patient transferred from bed {from_bed.id} to bed {to_bed_id}"
        + (f": {reason}" if reason else ""),
        old_value={"bed_id": from_bed.id},
        new_value={"bed_id": to_bed_id},
    )
    return transfer


def get_current_bed(admission: Admission) -> Bed:
    """Derives the admission's current bed from transfer history."""
    latest_transfer = (
        WardTransfer.query.filter_by(admission_id=admission.id)
        .order_by(WardTransfer.transferred_at.desc())
        .first()
    )
    return latest_transfer.to_bed if latest_transfer else admission.bed


@transactional
def discharge_patient(admission_id: int, reason: str | None = None) -> Admission:
    admission = get_admission(admission_id)
    if admission.status != AdmissionStatus.ADMITTED:
        raise ConflictError(f"Admission {admission_id} is not active ('{admission.status.value}')")

    current_bed = get_current_bed(admission)
    current_bed.status = BedStatus.AVAILABLE

    old_status = admission.status.value
    admission.status = AdmissionStatus.DISCHARGED
    admission.discharged_at = _utcnow()
    if reason:
        admission.reason = f"{admission.reason or ''}\nDischarge note: {reason}".strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Admission",
        entity_id=admission.id,
        description="Patient discharged" + (f": {reason}" if reason else ""),
        old_value={"status": old_status},
        new_value={"status": admission.status.value},
    )
    return admission


 # NOTE: setting status=TRANSFERRED here matches your enum's
    # AdmissionStatus.TRANSFERRED value existing at all, but it means
    # get_active_admission_for_patient() (which filters on ADMITTED)
    # would stop finding this admission after a transfer, which is
    # almost certainly wrong — a transferred patient is still admitted,
    # just in a different bed. Flagging this as a real ambiguity in
    # the enum's intended meaning rather than guessing: if TRANSFERRED
    # is meant to be a permanent status change, active-admission
    # lookups need to check status.in_([ADMITTED, TRANSFERRED]).
    # I'm implementing the safer interpretation here — reverting
    # status back to ADMITTED after logging the transfer — so the
    # patient doesn't disappear from "active admissions" queries.