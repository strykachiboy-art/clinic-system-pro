from datetime import date

from app.extensions import db

from app.core.utils.decorators import transactional
from app.core.utils.qrcode_util import generate_tracking_code

from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)

from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction

from app.modules.clinic.services.clinic_service import (
    ensure_clinic_active,
)

from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
    PatientInsurance,
    PatientVitals,
)


_EDITABLE_PATIENT_FIELDS = {
    "first_name",
    "last_name",
    "date_of_birth",
    "gender",
    "blood_type",
    "phone",
    "email",
    "address",
    "allergies",
    "chronic_conditions",
    "emirates_id",
    "umrn",
}


# ---------------------------------------------------------------------
# Patient core
# ---------------------------------------------------------------------


def get_patient(patient_id: int) -> Patient:
    """
    Retrieve a patient regardless of the clinic's status.

    Historical patient records must remain retrievable even when
    the patient's clinic is inactive or suspended.
    """
    patient = Patient.query.get(patient_id)

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def list_patients(
    clinic_id: int | None = None,
    active_only: bool = True,
    search: str | None = None,
) -> list[Patient]:
    """
    List patients.

    This is intentionally a retrieval operation, so an inactive or
    suspended clinic can still have its historical patient records
    retrieved.
    """
    query = Patient.query

    if clinic_id is not None:
        query = query.filter_by(
            clinic_id=clinic_id,
        )

    if active_only:
        query = query.filter_by(
            is_active=True,
        )

    if search:
        like = f"%{search.strip()}%"

        query = query.filter(
            db.or_(
                Patient.first_name.ilike(like),
                Patient.last_name.ilike(like),
                Patient.patient_number.ilike(like),
            )
        )

    return (
        query
        .order_by(
            Patient.last_name.asc(),
            Patient.first_name.asc(),
        )
        .all()
    )


def _generate_patient_number(
    clinic_id: int,
) -> str:
    """
    Generate a collision-safe patient number for a clinic.
    """
    code = generate_tracking_code(
        prefix=f"PT{clinic_id}",
    )

    for _ in range(5):
        if not Patient.query.filter_by(
            patient_number=code,
        ).first():
            return code

        code = generate_tracking_code(
            prefix=f"PT{clinic_id}",
        )

    raise ConflictError(
        "Could not generate a unique patient number, "
        "try again"
    )


@transactional
def create_patient(
    clinic_id: int,
    first_name: str,
    last_name: str,
    **fields,
) -> Patient:
    """
    Register a new patient.

    New patients can only be registered under an ACTIVE clinic.
    """
    clinic = ensure_clinic_active(
        clinic_id,
    )

    if not first_name or not first_name.strip():
        raise ValidationError(
            "First name is required"
        )

    if not last_name or not last_name.strip():
        raise ValidationError(
            "Last name is required"
        )

    dob = fields.get("date_of_birth")

    if dob and dob > date.today():
        raise ValidationError(
            "Date of birth cannot be in the future"
        )

    unknown = (
        set(fields)
        - _EDITABLE_PATIENT_FIELDS
    )

    if unknown:
        raise ValidationError(
            "Unknown patient field(s): "
            + ", ".join(sorted(unknown))
        )

    patient = Patient(
        clinic_id=clinic.id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        patient_number=_generate_patient_number(
            clinic.id,
        ),
        **fields,
    )

    db.session.add(patient)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=patient.id,
        description=(
            f"Patient '{patient.first_name} "
            f"{patient.last_name}' registered "
            f"({patient.patient_number})"
        ),
        new_value={
            "clinic_id": clinic.id,
            "patient_number": patient.patient_number,
        },
    )

    return patient


@transactional
def update_patient(
    patient_id: int,
    **fields,
) -> Patient:
    """
    Update patient information.

    Patient information cannot be modified through an inactive
    or suspended clinic.
    """
    patient = get_patient(
        patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    unknown = (
        set(fields)
        - _EDITABLE_PATIENT_FIELDS
    )

    if unknown:
        raise ValidationError(
            "Unknown patient field(s): "
            + ", ".join(sorted(unknown))
        )

    dob = fields.get("date_of_birth")

    if dob and dob > date.today():
        raise ValidationError(
            "Date of birth cannot be in the future"
        )

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(
            patient,
            key,
        )

        if current_val == new_val:
            continue

        old_value[key] = (
            current_val.value
            if hasattr(current_val, "value")
            else current_val
        )

        new_value[key] = (
            new_val.value
            if hasattr(new_val, "value")
            else new_val
        )

        setattr(
            patient,
            key,
            new_val,
        )

    if not new_value:
        return patient

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Patient",
        entity_id=patient.id,
        description=(
            f"Patient '{patient.first_name} "
            f"{patient.last_name}' updated"
        ),
        old_value=old_value,
        new_value=new_value,
    )

    return patient


@transactional
def set_active_status(
    patient_id: int,
    is_active: bool,
) -> Patient:
    """
    Activate or deactivate a patient.

    Patient records are never hard-deleted because they may have
    clinical history.

    The clinic itself must be ACTIVE before this operational
    change can be performed.
    """
    patient = get_patient(
        patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    if patient.is_active == is_active:
        return patient

    old_status = patient.is_active

    patient.is_active = is_active

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Patient",
        entity_id=patient.id,
        description=(
            f"Patient "
            f"{'reactivated' if is_active else 'deactivated'}"
        ),
        old_value={
            "is_active": old_status,
        },
        new_value={
            "is_active": is_active,
        },
    )

    return patient


# ---------------------------------------------------------------------
# Family / emergency contacts
# ---------------------------------------------------------------------


def list_family_members(
    patient_id: int,
) -> list[PatientFamilyMember]:
    """
    Retrieve family/emergency contacts.

    Retrieval remains available for historical patients.
    """
    get_patient(
        patient_id,
    )

    return (
        PatientFamilyMember.query
        .filter_by(
            patient_id=patient_id,
        )
        .all()
    )


@transactional
def add_family_member(
    patient_id: int,
    full_name: str,
    relation,
    related_patient_id: int | None = None,
    **fields,
) -> PatientFamilyMember:
    """
    Add a family/emergency contact.

    This is a write operation, so the patient's clinic must be ACTIVE.
    """
    patient = get_patient(
        patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    if not full_name or not full_name.strip():
        raise ValidationError(
            "Family member name is required"
        )

    related_patient = None

    if related_patient_id is not None:
        if related_patient_id == patient_id:
            raise ValidationError(
                "A patient cannot be linked as "
                "their own family member"
            )

        related_patient = get_patient(
            related_patient_id,
        )

        if related_patient.clinic_id != patient.clinic_id:
            raise ValidationError(
                "Related patient must belong to "
                "the same clinic"
            )

    member = PatientFamilyMember(
        patient_id=patient.id,
        full_name=full_name.strip(),
        relation=relation,
        related_patient_id=(
            related_patient.id
            if related_patient is not None
            else None
        ),
        **fields,
    )

    db.session.add(member)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientFamilyMember",
        entity_id=member.id,
        description=(
            f"Family member '{member.full_name}' "
            f"({relation.value}) added for "
            f"patient {patient_id}"
        ),
        new_value={
            "patient_id": patient_id,
            "full_name": member.full_name,
            "relation": relation.value,
        },
    )

    return member


@transactional
def update_family_member(
    member_id: int,
    **fields,
) -> PatientFamilyMember:
    """
    Update a family/emergency contact.
    """
    member = PatientFamilyMember.query.get(
        member_id,
    )

    if member is None:
        raise NotFoundError(
            f"Family member {member_id} not found"
        )

    patient = get_patient(
        member.patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(
            member,
            key,
        )

        if current_val == new_val:
            continue

        old_value[key] = (
            current_val.value
            if hasattr(current_val, "value")
            else current_val
        )

        new_value[key] = (
            new_val.value
            if hasattr(new_val, "value")
            else new_val
        )

        setattr(
            member,
            key,
            new_val,
        )

    if not new_value:
        return member

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="PatientFamilyMember",
        entity_id=member.id,
        description=(
            f"Family member '{member.full_name}' "
            f"updated"
        ),
        old_value=old_value,
        new_value=new_value,
    )

    return member


@transactional
def remove_family_member(
    member_id: int,
) -> None:
    """
    Remove a family/emergency contact.

    The contact itself can be deleted because it is not the patient's
    clinical record. The operation still requires an ACTIVE clinic.
    """
    member = PatientFamilyMember.query.get(
        member_id,
    )

    if member is None:
        raise NotFoundError(
            f"Family member {member_id} not found"
        )

    patient = get_patient(
        member.patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    create_audit_log(
        action=AuditAction.DELETE,
        entity_type="PatientFamilyMember",
        entity_id=member.id,
        description=(
            f"Family member '{member.full_name}' "
            f"removed from patient {member.patient_id}"
        ),
        old_value={
            "full_name": member.full_name,
            "relation": member.relation.value,
        },
    )

    db.session.delete(
        member,
    )


# ---------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------


def list_insurances(
    patient_id: int,
    active_only: bool = True,
) -> list[PatientInsurance]:
    """
    Retrieve patient insurance records.

    Retrieval remains available regardless of clinic status.
    """
    get_patient(
        patient_id,
    )

    query = (
        PatientInsurance.query
        .filter_by(
            patient_id=patient_id,
        )
    )

    if active_only:
        query = query.filter_by(
            is_active=True,
        )

    return query.all()


@transactional
def add_insurance(
    patient_id: int,
    provider_name: str,
    policy_number: str,
    is_primary: bool = True,
    **fields,
) -> PatientInsurance:
    """
    Add insurance coverage to a patient.

    The patient's clinic must be ACTIVE.
    """
    patient = get_patient(
        patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    if not provider_name or not provider_name.strip():
        raise ValidationError(
            "Insurance provider name is required"
        )

    if not policy_number or not policy_number.strip():
        raise ValidationError(
            "Policy number is required"
        )

    if is_primary:
        PatientInsurance.query.filter_by(
            patient_id=patient.id,
            is_primary=True,
        ).update(
            {
                "is_primary": False,
            }
        )

    insurance = PatientInsurance(
        patient_id=patient.id,
        provider_name=provider_name.strip(),
        policy_number=policy_number.strip(),
        is_primary=is_primary,
        **fields,
    )

    db.session.add(
        insurance,
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientInsurance",
        entity_id=insurance.id,
        description=(
            f"Insurance '{insurance.provider_name}' "
            f"added for patient {patient_id}"
        ),
        new_value={
            "patient_id": patient_id,
            "provider_name": insurance.provider_name,
            "policy_number": insurance.policy_number,
            "is_primary": is_primary,
        },
    )

    return insurance


@transactional
def update_insurance(
    insurance_id: int,
    **fields,
) -> PatientInsurance:
    """
    Update patient insurance.

    The patient's clinic must be ACTIVE.
    """
    insurance = PatientInsurance.query.get(
        insurance_id,
    )

    if insurance is None:
        raise NotFoundError(
            f"Insurance record {insurance_id} not found"
        )

    patient = get_patient(
        insurance.patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    if fields.get("is_primary") is True:
        (
            PatientInsurance.query
            .filter(
                PatientInsurance.patient_id
                == insurance.patient_id,
                PatientInsurance.id
                != insurance.id,
            )
            .update(
                {
                    "is_primary": False,
                }
            )
        )

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(
            insurance,
            key,
        )

        if current_val == new_val:
            continue

        old_value[key] = (
            current_val.value
            if hasattr(current_val, "value")
            else current_val
        )

        new_value[key] = (
            new_val.value
            if hasattr(new_val, "value")
            else new_val
        )

        setattr(
            insurance,
            key,
            new_val,
        )

    if not new_value:
        return insurance

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="PatientInsurance",
        entity_id=insurance.id,
        description=(
            f"Insurance '{insurance.provider_name}' "
            f"updated"
        ),
        old_value=old_value,
        new_value=new_value,
    )

    return insurance


# ---------------------------------------------------------------------
# Vitals — append-only log, no update/delete by design
# ---------------------------------------------------------------------


def get_vitals_history(
    patient_id: int,
    limit: int | None = None,
) -> list[PatientVitals]:
    """
    Retrieve the patient's vitals history.

    Historical vitals remain retrievable even if the clinic is
    inactive or suspended.
    """
    get_patient(
        patient_id,
    )

    query = (
        PatientVitals.query
        .filter_by(
            patient_id=patient_id,
        )
        .order_by(
            PatientVitals.recorded_at.desc(),
        )
    )

    if limit:
        query = query.limit(
            limit,
        )

    return query.all()


def get_latest_vitals(
    patient_id: int,
) -> PatientVitals | None:
    """
    Retrieve the patient's latest vitals.

    Historical retrieval remains available regardless of clinic status.
    """
    get_patient(
        patient_id,
    )

    return (
        PatientVitals.query
        .filter_by(
            patient_id=patient_id,
        )
        .order_by(
            PatientVitals.recorded_at.desc(),
        )
        .first()
    )


@transactional
def record_vitals(
    patient_id: int,
    **fields,
) -> PatientVitals:
    """
    Record a new vitals entry.

    New clinical information can only be recorded while the patient's
    clinic is ACTIVE.
    """
    patient = get_patient(
        patient_id,
    )

    ensure_clinic_active(
        patient.clinic_id,
    )

    measurement_fields = (
        "temperature_c",
        "blood_pressure_systolic",
        "blood_pressure_diastolic",
        "heart_rate_bpm",
        "respiratory_rate",
        "oxygen_saturation",
        "weight_kg",
        "height_cm",
    )

    if not any(
        fields.get(field) is not None
        for field in measurement_fields
    ):
        raise ValidationError(
            "At least one vital measurement "
            "must be provided"
        )

    vitals = PatientVitals(
        patient_id=patient.id,
        **fields,
    )

    db.session.add(
        vitals,
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PatientVitals",
        entity_id=vitals.id,
        description=(
            f"Vitals recorded for patient "
            f"{patient_id}"
        ),
        new_value={
            key: str(value)
            for key, value in fields.items()
            if value is not None
        },
    )

    return vitals