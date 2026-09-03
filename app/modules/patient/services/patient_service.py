from datetime import date
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.utils.qrcode_util import generate_tracking_code
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.modules.patient.models.patient_model import (
    Patient, PatientFamilyMember, PatientInsurance, PatientVitals,
)

_EDITABLE_PATIENT_FIELDS = {
    "first_name", "last_name", "date_of_birth", "gender", "blood_type",
    "phone", "email", "address", "allergies", "chronic_conditions",
}


# ---------------------------------------------------------------------
# Patient core
# ---------------------------------------------------------------------

def get_patient(patient_id: int) -> Patient:
    patient = Patient.query.get(patient_id)
    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found")
    return patient


def list_patients(clinic_id: int | None = None, active_only: bool = True, search: str | None = None) -> list[Patient]:
    query = Patient.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    if active_only:
        query = query.filter_by(is_active=True)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            db.or_(Patient.first_name.ilike(like), Patient.last_name.ilike(like), Patient.patient_number.ilike(like))
        )
    return query.order_by(Patient.last_name, Patient.first_name).all()


def _generate_patient_number(clinic_id: int) -> str:
    # Reuses the same collision-safe generator pattern as lab order QR
    # codes — random + retry beats a count()-based scheme, which races
    # under concurrent registrations. Function name is generic on
    # purpose despite living in a "qrcode_util" module; worth splitting
    # into a plain id_generator util if a third caller needs this.
    code = generate_tracking_code(prefix=f"PT{clinic_id}")
    for _ in range(5):
        if not Patient.query.filter_by(patient_number=code).first():
            return code
        code = generate_tracking_code(prefix=f"PT{clinic_id}")
    raise ConflictError("Could not generate a unique patient number, try again")


@transactional
def create_patient(clinic_id: int, first_name: str, last_name: str, **fields) -> Patient:
    if not first_name or not first_name.strip():
        raise ValidationError("First name is required")
    if not last_name or not last_name.strip():
        raise ValidationError("Last name is required")

    dob = fields.get("date_of_birth")
    if dob and dob > date.today():
        raise ValidationError("Date of birth cannot be in the future")

    unknown = set(fields) - _EDITABLE_PATIENT_FIELDS
    if unknown:
        raise ValidationError(f"Unknown patient field(s): {', '.join(sorted(unknown))}")

    patient = Patient(
        clinic_id=clinic_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        patient_number=_generate_patient_number(clinic_id),
        **fields,
    )
    db.session.add(patient)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=patient.id,
        description=f"Patient '{patient.first_name} {patient.last_name}' registered ({patient.patient_number})",
        new_value={"patient_number": patient.patient_number},
    )
    return patient


@transactional
def update_patient(patient_id: int, **fields) -> Patient:
    patient = get_patient(patient_id)

    unknown = set(fields) - _EDITABLE_PATIENT_FIELDS
    if unknown:
        raise ValidationError(f"Unknown patient field(s): {', '.join(sorted(unknown))}")

    dob = fields.get("date_of_birth")
    if dob and dob > date.today():
        raise ValidationError("Date of birth cannot be in the future")

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(patient, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(patient, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Patient",
            entity_id=patient.id,
            description=f"Patient '{patient.first_name} {patient.last_name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return patient


@transactional
def set_active_status(patient_id: int, is_active: bool) -> Patient:
    """No hard delete — a patient with clinical history should never be
    erased, only deactivated (e.g. transferred out, deceased, duplicate)."""
    patient = get_patient(patient_id)
    if patient.is_active == is_active:
        return patient

    patient.is_active = is_active
    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Patient",
        entity_id=patient.id,
        description=f"Patient {'reactivated' if is_active else 'deactivated'}",
        new_value={"is_active": is_active},
    )
    return patient


# ---------------------------------------------------------------------
# Family / emergency contacts
# ---------------------------------------------------------------------

def list_family_members(patient_id: int) -> list[PatientFamilyMember]:
    get_patient(patient_id)  # 404s if patient doesn't exist
    return PatientFamilyMember.query.filter_by(patient_id=patient_id).all()


@transactional
def add_family_member(patient_id: int, full_name: str, relation, related_patient_id: int | None = None, **fields) -> PatientFamilyMember:
    patient = get_patient(patient_id)

    if not full_name or not full_name.strip():
        raise ValidationError("Family member name is required")

    if related_patient_id is not None:
        if related_patient_id == patient_id:
            raise ValidationError("A patient cannot be linked as their own family member")
        get_patient(related_patient_id)  # 404s if the linked patient doesn't exist

    member = PatientFamilyMember(
        patient_id=patient_id,
        full_name=full_name.strip(),
        relation=relation,
        related_patient_id=related_patient_id,
        **fields,
    )
    db.session.add(member)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientFamilyMember",
        entity_id=member.id,
        description=f"Family member '{member.full_name}' ({relation.value}) added for patient {patient_id}",
        new_value={"full_name": member.full_name, "relation": relation.value},
    )
    return member


@transactional
def update_family_member(member_id: int, **fields) -> PatientFamilyMember:
    member = PatientFamilyMember.query.get(member_id)
    if member is None:
        raise NotFoundError(f"Family member {member_id} not found")

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(member, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(member, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="PatientFamilyMember",
            entity_id=member.id,
            description=f"Family member '{member.full_name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return member


@transactional
def remove_family_member(member_id: int) -> None:
    member = PatientFamilyMember.query.get(member_id)
    if member is None:
        raise NotFoundError(f"Family member {member_id} not found")

    create_audit_log(
        action=AuditAction.DELETE,
        entity_type="PatientFamilyMember",
        entity_id=member.id,
        description=f"Family member '{member.full_name}' removed from patient {member.patient_id}",
        old_value={"full_name": member.full_name, "relation": member.relation.value},
    )
    db.session.delete(member)


# ---------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------

def list_insurances(patient_id: int, active_only: bool = True) -> list[PatientInsurance]:
    get_patient(patient_id)
    query = PatientInsurance.query.filter_by(patient_id=patient_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.all()


@transactional
def add_insurance(patient_id: int, provider_name: str, policy_number: str, is_primary: bool = True, **fields) -> PatientInsurance:
    get_patient(patient_id)

    if not provider_name or not provider_name.strip():
        raise ValidationError("Insurance provider name is required")
    if not policy_number or not policy_number.strip():
        raise ValidationError("Policy number is required")

    # Enforced design decision: exactly one primary policy per patient.
    # Setting a new primary silently demotes the previous one — if
    # simultaneous dual-primary coverage is a real use case, drop this.
    if is_primary:
        PatientInsurance.query.filter_by(patient_id=patient_id, is_primary=True).update(
            {"is_primary": False}
        )

    insurance = PatientInsurance(
        patient_id=patient_id,
        provider_name=provider_name.strip(),
        policy_number=policy_number.strip(),
        is_primary=is_primary,
        **fields,
    )
    db.session.add(insurance)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientInsurance",
        entity_id=insurance.id,
        description=f"Insurance '{insurance.provider_name}' added for patient {patient_id}",
        new_value={"provider_name": insurance.provider_name, "policy_number": insurance.policy_number, "is_primary": is_primary},
    )
    return insurance


@transactional
def update_insurance(insurance_id: int, **fields) -> PatientInsurance:
    insurance = PatientInsurance.query.get(insurance_id)
    if insurance is None:
        raise NotFoundError(f"Insurance record {insurance_id} not found")

    if fields.get("is_primary") is True:
        PatientInsurance.query.filter(
            PatientInsurance.patient_id == insurance.patient_id,
            PatientInsurance.id != insurance.id,
        ).update({"is_primary": False})

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(insurance, key)
        if current_val != new_val:
            old_value[key] = current_val
            new_value[key] = new_val
            setattr(insurance, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="PatientInsurance",
            entity_id=insurance.id,
            description=f"Insurance '{insurance.provider_name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return insurance


# ---------------------------------------------------------------------
# Vitals — append-only log, no update/delete by design
# ---------------------------------------------------------------------

def get_vitals_history(patient_id: int, limit: int | None = None) -> list[PatientVitals]:
    get_patient(patient_id)
    query = PatientVitals.query.filter_by(patient_id=patient_id).order_by(PatientVitals.recorded_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_latest_vitals(patient_id: int) -> PatientVitals | None:
    get_patient(patient_id)
    return (
        PatientVitals.query.filter_by(patient_id=patient_id)
        .order_by(PatientVitals.recorded_at.desc())
        .first()
    )


@transactional
def record_vitals(patient_id: int, **fields) -> PatientVitals:
    get_patient(patient_id)

    if not any(fields.get(k) is not None for k in (
        "temperature_c", "blood_pressure_systolic", "blood_pressure_diastolic",
        "heart_rate_bpm", "respiratory_rate", "oxygen_saturation", "weight_kg", "height_cm",
    )):
        raise ValidationError("At least one vital measurement must be provided")

    vitals = PatientVitals(patient_id=patient_id, **fields)
    db.session.add(vitals)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientVitals",
        entity_id=vitals.id,
        description=f"Vitals recorded for patient {patient_id}",
        new_value={k: str(v) for k, v in fields.items() if v is not None},
    )
    return vitals