from datetime import datetime, timezone
from itertools import combinations

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.prescription_enums import (
    DrugInteractionSeverity,
    PrescriptionStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.patient.models.patient_model import Patient
from app.modules.pharmacy.models.pharmacy_model import Drug
from app.modules.prescription.models.prescription_model import (
    DrugInteraction,
    Prescription,
    PrescriptionItem,
)
from app.modules.staff.models.staff_model import Staff


# =====================================================================
# Date/time helpers
# =====================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(
    value: datetime | None,
) -> datetime | None:
    """
    Normalize incoming datetimes to UTC.

    Naive datetimes are interpreted as UTC for backwards compatibility
    with existing API clients.
    """
    if value is None:
        return None

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# =====================================================================
# Clinic validation
# =====================================================================

def _ensure_clinic_active(
    clinic_id: int,
) -> Clinic:
    """
    Prescription writes are allowed only for ACTIVE clinics.

    Historical reads intentionally do not use this function.
    """
    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic


# =====================================================================
# Entity retrieval helpers
# =====================================================================

def _get_patient(
    patient_id: int,
) -> Patient:
    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_staff(
    staff_id: int,
) -> Staff:
    staff = db.session.get(
        Staff,
        staff_id,
    )

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def _get_consultation(
    consultation_id: int,
) -> Consultation:
    consultation = db.session.get(
        Consultation,
        consultation_id,
    )

    if consultation is None:
        raise NotFoundError(
            f"Consultation {consultation_id} not found"
        )

    return consultation


def _get_drug(
    drug_id: int,
) -> Drug:
    drug = db.session.get(
        Drug,
        drug_id,
    )

    if drug is None:
        raise NotFoundError(
            f"Drug {drug_id} not found"
        )

    return drug


# =====================================================================
# Ownership / business validation
# =====================================================================

def _validate_patient_for_clinic(
    patient_id: int,
    clinic_id: int,
) -> Patient:
    patient = _get_patient(
        patient_id
    )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            f"Patient {patient_id} does not belong "
            f"to clinic {clinic_id}"
        )

    if not patient.is_active:
        raise ValidationError(
            f"Patient {patient_id} is inactive"
        )

    return patient


def _validate_prescriber(
    prescribed_by_id: int,
    clinic_id: int,
) -> Staff:
    """
    Validate that the prescriber is:
    - a staff member of the clinic
    - active
    - linked to an active user
    - assigned the DOCTOR role
    """
    staff = _get_staff(
        prescribed_by_id
    )

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            f"Prescriber {prescribed_by_id} does not belong "
            f"to clinic {clinic_id}"
        )

    if staff.status.value != "active":
        raise ValidationError(
            f"Prescriber {prescribed_by_id} is not active"
        )

    if staff.user is None:
        raise ValidationError(
            f"Prescriber {prescribed_by_id} has no linked user account"
        )

    if not staff.user.is_active:
        raise ValidationError(
            f"Prescriber {prescribed_by_id}'s user account is inactive"
        )

    if staff.user.role != Role.DOCTOR:
        raise ValidationError(
            "Only doctors can prescribe medication"
        )

    return staff


def _validate_consultation(
    consultation_id: int | None,
    clinic_id: int,
    patient_id: int,
) -> Consultation | None:
    if consultation_id is None:
        return None

    consultation = _get_consultation(
        consultation_id
    )

    if consultation.clinic_id != clinic_id:
        raise ValidationError(
            f"Consultation {consultation_id} does not belong "
            f"to clinic {clinic_id}"
        )

    if consultation.patient_id != patient_id:
        raise ValidationError(
            f"Consultation {consultation_id} does not belong "
            f"to patient {patient_id}"
        )

    return consultation


def _validate_drug_for_clinic(
    drug_id: int,
    clinic_id: int,
) -> Drug:
    """
    A prescription may use:
    - global drugs where Drug.clinic_id is NULL
    - drugs owned by the current clinic
    """
    drug = _get_drug(
        drug_id
    )

    if not drug.is_active:
        raise ValidationError(
            f"Drug {drug_id} is inactive"
        )

    if (
        drug.clinic_id is not None
        and drug.clinic_id != clinic_id
    ):
        raise ValidationError(
            f"Drug {drug_id} does not belong "
            f"to clinic {clinic_id}"
        )

    return drug


def _validate_expiry(
    expires_at: datetime | None,
) -> datetime | None:
    expires_at = _normalize_datetime(
        expires_at
    )

    if expires_at is None:
        return None

    if expires_at <= _utcnow():
        raise ValidationError(
            "Prescription expiry time must be in the future"
        )

    return expires_at


def _validate_items(
    items: list[dict],
    clinic_id: int,
) -> list[Drug]:
    if not items:
        raise ValidationError(
            "A prescription must include at least one item"
        )

    seen_drug_ids: set[int] = set()
    drugs: list[Drug] = []

    for index, entry in enumerate(
        items,
        start=1,
    ):
        if not isinstance(entry, dict):
            raise ValidationError(
                f"Prescription item {index} must be an object"
            )

        drug_id = entry.get(
            "drug_id"
        )

        if (
            not isinstance(drug_id, int)
            or isinstance(drug_id, bool)
        ):
            raise ValidationError(
                f"Prescription item {index} has an invalid drug_id"
            )

        if drug_id <= 0:
            raise ValidationError(
                f"Prescription item {index} has an invalid drug_id"
            )

        if drug_id in seen_drug_ids:
            raise ValidationError(
                f"Drug {drug_id} appears more than once "
                "in the prescription"
            )

        quantity = entry.get(
            "quantity"
        )

        if quantity is not None:
            if (
                not isinstance(quantity, int)
                or isinstance(quantity, bool)
                or quantity <= 0
            ):
                raise ValidationError(
                    f"Quantity for drug {drug_id} "
                    "must be greater than zero"
                )

        drug = _validate_drug_for_clinic(
            drug_id=drug_id,
            clinic_id=clinic_id,
        )

        seen_drug_ids.add(
            drug_id
        )
        drugs.append(
            drug
        )

    return drugs


# =====================================================================
# Drug interactions
# =====================================================================

def _normalize_interaction_pair(
    drug_a_id: int,
    drug_b_id: int,
) -> tuple[int, int]:
    if drug_a_id == drug_b_id:
        raise ValidationError(
            "A drug cannot interact with itself"
        )

    return tuple(
        sorted(
            (
                drug_a_id,
                drug_b_id,
            )
        )
    )


def find_interaction(
    drug_a_id: int,
    drug_b_id: int,
) -> DrugInteraction | None:
    drug_a_id, drug_b_id = _normalize_interaction_pair(
        drug_a_id,
        drug_b_id,
    )

    return (
        DrugInteraction.query
        .filter(
            DrugInteraction.drug_a_id == drug_a_id,
            DrugInteraction.drug_b_id == drug_b_id,
        )
        .first()
    )


def _validate_interaction_drugs_for_clinic(
    drug_ids: list[int],
    clinic_id: int,
) -> list[Drug]:
    """
    Validate all drugs participating in an interaction check.

    Both global drugs and drugs belonging to the authenticated clinic
    are allowed. Drugs belonging to another clinic are rejected.
    """
    drugs: list[Drug] = []

    for drug_id in drug_ids:
        drugs.append(
            _validate_drug_for_clinic(
                drug_id=drug_id,
                clinic_id=clinic_id,
            )
        )

    return drugs


@transactional
def create_drug_interaction(
    drug_a_id: int,
    drug_b_id: int,
    severity: DrugInteractionSeverity,
    description: str | None = None,
) -> DrugInteraction:
    """
    Drug interactions are global because DrugInteraction has no clinic_id.
    Therefore only global drugs can participate.
    """

    drug_a_id, drug_b_id = _normalize_interaction_pair(
        drug_a_id,
        drug_b_id,
    )

    drug_a = _get_drug(
        drug_a_id
    )

    drug_b = _get_drug(
        drug_b_id
    )

    if drug_a.clinic_id is not None:
        raise ValidationError(
            f"Drug {drug_a_id} is clinic-specific and cannot "
            "be used in a global drug interaction"
        )

    if drug_b.clinic_id is not None:
        raise ValidationError(
            f"Drug {drug_b_id} is clinic-specific and cannot "
            "be used in a global drug interaction"
        )

    if not drug_a.is_active:
        raise ValidationError(
            f"Drug {drug_a_id} is inactive"
        )

    if not drug_b.is_active:
        raise ValidationError(
            f"Drug {drug_b_id} is inactive"
        )

    existing = (
        DrugInteraction.query
        .filter(
            DrugInteraction.drug_a_id == drug_a_id,
            DrugInteraction.drug_b_id == drug_b_id,
        )
        .with_for_update()
        .first()
    )

    if existing is not None:
        raise ConflictError(
            f"An interaction between drugs "
            f"{drug_a_id} and {drug_b_id} already exists"
        )

    interaction = DrugInteraction(
        drug_a_id=drug_a_id,
        drug_b_id=drug_b_id,
        severity=severity,
        description=description,
    )

    db.session.add(
        interaction
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DrugInteraction",
        entity_id=interaction.id,
        description=(
            f"Drug interaction added: "
            f"{drug_a_id} x {drug_b_id} "
            f"({severity.value})"
        ),
        new_value={
            "drug_a_id": drug_a_id,
            "drug_b_id": drug_b_id,
            "severity": severity.value,
            "description": description,
        },
    )

    return interaction


def check_interactions(
    drug_ids: list[int],
    clinic_id: int,
) -> list[dict]:
    """
    Return known interaction warnings for drugs accessible
    to the authenticated clinic.

    Interaction pairs are treated as unordered:
    A-B == B-A.
    """
    if not isinstance(
        drug_ids,
        list,
    ):
        raise ValidationError(
            "drug_ids must be a list"
        )

    if not drug_ids:
        return []

    for drug_id in drug_ids:
        if (
            not isinstance(drug_id, int)
            or isinstance(drug_id, bool)
            or drug_id <= 0
        ):
            raise ValidationError(
                "All drug IDs must be greater than zero"
            )

    unique_drug_ids = sorted(
        set(drug_ids)
    )

    if len(unique_drug_ids) < 2:
        return []

    _validate_interaction_drugs_for_clinic(
        drug_ids=unique_drug_ids,
        clinic_id=clinic_id,
    )

    found: list[dict] = []

    for drug_a_id, drug_b_id in combinations(
        unique_drug_ids,
        2,
    ):
        interaction = find_interaction(
            drug_a_id,
            drug_b_id,
        )

        if interaction is not None:
            found.append(
                {
                    "drug_a_id": interaction.drug_a_id,
                    "drug_b_id": interaction.drug_b_id,
                    "severity": interaction.severity.value,
                    "description": interaction.description,
                }
            )

    return found


# =====================================================================
# Prescription retrieval
# =====================================================================

def get_prescription(
    prescription_id: int,
) -> Prescription:
    """
    Historical read.

    Inactive/suspended clinics remain readable.
    Clinic ownership is enforced by the route/service caller.
    """
    prescription = db.session.get(
        Prescription,
        prescription_id,
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {prescription_id} not found"
        )

    return prescription


def _get_prescription_for_update(
    prescription_id: int,
) -> Prescription:
    """
    Retrieve a prescription with a row lock for lifecycle mutation.
    """
    prescription = (
        Prescription.query
        .filter(
            Prescription.id == prescription_id
        )
        .with_for_update()
        .first()
    )

    if prescription is None:
        raise NotFoundError(
            f"Prescription {prescription_id} not found"
        )

    return prescription


def _validate_prescription_clinic(
    prescription: Prescription,
    clinic_id: int,
) -> None:
    """
    Enforce tenant isolation for prescription operations.
    """
    if prescription.clinic_id != clinic_id:
        raise ValidationError(
            f"Prescription {prescription.id} does not belong "
            f"to clinic {clinic_id}"
        )


def list_prescriptions_for_patient(
    patient_id: int,
    clinic_id: int,
    active_only: bool = False,
) -> list[Prescription]:
    """
    Clinic-scoped historical prescription lookup.
    """
    _validate_patient_for_clinic(
        patient_id=patient_id,
        clinic_id=clinic_id,
    )

    query = Prescription.query.filter(
        Prescription.patient_id == patient_id,
        Prescription.clinic_id == clinic_id,
    )

    if active_only:
        query = query.filter(
            Prescription.status
            == PrescriptionStatus.ACTIVE
        )

    return (
        query
        .order_by(
            Prescription.issued_at.desc()
        )
        .all()
    )


# =====================================================================
# Prescription creation
# =====================================================================

@transactional
def create_prescription(
    clinic_id: int,
    patient_id: int,
    prescribed_by_id: int,
    items: list[dict],
    consultation_id: int | None = None,
    expires_at: datetime | None = None,
    notes: str | None = None,
) -> tuple[Prescription, list[dict]]:
    """
    Create a prescription for a patient.

    Returns:
        (prescription, interaction_warnings)
    """

    _ensure_clinic_active(
        clinic_id
    )

    _validate_patient_for_clinic(
        patient_id=patient_id,
        clinic_id=clinic_id,
    )

    _validate_prescriber(
        prescribed_by_id=prescribed_by_id,
        clinic_id=clinic_id,
    )

    _validate_consultation(
        consultation_id=consultation_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
    )

    expires_at = _validate_expiry(
        expires_at
    )

    drugs = _validate_items(
        items=items,
        clinic_id=clinic_id,
    )

    drug_ids = [
        drug.id
        for drug in drugs
    ]

    warnings = check_interactions(
        drug_ids=drug_ids,
        clinic_id=clinic_id,
    )

    prescription = Prescription(
        clinic_id=clinic_id,
        patient_id=patient_id,
        consultation_id=consultation_id,
        prescribed_by_id=prescribed_by_id,
        status=PrescriptionStatus.ACTIVE,
        notes=notes,
        issued_at=_utcnow(),
        expires_at=expires_at,
    )

    db.session.add(
        prescription
    )

    db.session.flush()

    for entry in items:
        prescription_item = PrescriptionItem(
            prescription_id=prescription.id,
            drug_id=entry["drug_id"],
            dosage=entry.get("dosage"),
            frequency=entry.get("frequency"),
            duration=entry.get("duration"),
            quantity=entry.get("quantity"),
            instructions=entry.get("instructions"),
        )

        db.session.add(
            prescription_item
        )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description=(
            f"Prescription created for patient "
            f"{patient_id} ({len(items)} item(s))"
            + (
                f" — {len(warnings)} interaction warning(s)"
                if warnings
                else ""
            )
        ),
        new_value={
            "clinic_id": clinic_id,
            "patient_id": patient_id,
            "prescribed_by_id": prescribed_by_id,
            "consultation_id": consultation_id,
            "drug_ids": drug_ids,
            "interaction_warnings": warnings,
            "expires_at": (
                expires_at.isoformat()
                if expires_at
                else None
            ),
        },
    )

    return prescription, warnings


# =====================================================================
# Prescription lifecycle
# =====================================================================

def _assert_status(
    prescription: Prescription,
    *allowed: PrescriptionStatus,
) -> None:
    if prescription.status not in allowed:
        raise ConflictError(
            f"Prescription {prescription.id} is "
            f"'{prescription.status.value}', "
            f"expected one of "
            f"{[status.value for status in allowed]}"
        )


def _assert_not_expired(
    prescription: Prescription,
) -> None:
    """
    Prevent lifecycle operations from bypassing an expiry timestamp
    merely because the automated expiration job has not run yet.
    """
    if (
        prescription.status
        == PrescriptionStatus.ACTIVE
        and prescription.expires_at is not None
        and _normalize_datetime(
            prescription.expires_at
        ) <= _utcnow()
    ):
        raise ConflictError(
            f"Prescription {prescription.id} has expired"
        )


@transactional
def cancel_prescription(
    prescription_id: int,
    clinic_id: int,
    reason: str | None = None,
) -> Prescription:
    """
    Cancel a prescription belonging to the authenticated clinic.
    """

    _ensure_clinic_active(
        clinic_id
    )

    prescription = _get_prescription_for_update(
        prescription_id
    )

    _validate_prescription_clinic(
        prescription=prescription,
        clinic_id=clinic_id,
    )

    _assert_status(
        prescription,
        PrescriptionStatus.ACTIVE,
    )

    _assert_not_expired(
        prescription
    )

    old_status = prescription.status.value
    old_notes = prescription.notes

    prescription.status = (
        PrescriptionStatus.CANCELLED
    )

    if reason:
        existing_notes = (
            prescription.notes or ""
        )

        prescription.notes = (
            f"{existing_notes}\nCancelled: {reason}"
        ).strip()

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description=(
            "Prescription cancelled"
            + (
                f": {reason}"
                if reason
                else ""
            )
        ),
        old_value={
            "status": old_status,
            "notes": old_notes,
        },
        new_value={
            "status": prescription.status.value,
            "notes": prescription.notes,
        },
    )

    return prescription


@transactional
def complete_prescription(
    prescription_id: int,
    clinic_id: int,
) -> Prescription:
    """
    Complete a prescription belonging to the authenticated clinic.
    """

    _ensure_clinic_active(
        clinic_id
    )

    prescription = _get_prescription_for_update(
        prescription_id
    )

    _validate_prescription_clinic(
        prescription=prescription,
        clinic_id=clinic_id,
    )

    _assert_status(
        prescription,
        PrescriptionStatus.ACTIVE,
    )

    _assert_not_expired(
        prescription
    )

    old_status = prescription.status.value

    prescription.status = (
        PrescriptionStatus.COMPLETED
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description="Prescription marked completed",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": prescription.status.value,
        },
    )

    return prescription


# =====================================================================
# Automated prescription expiration
# =====================================================================

@transactional
def expire_stale_prescriptions() -> int:
    """
    Expire active prescriptions whose expiry time has passed.

    This operation is transactional. The transactional decorator owns
    the commit/rollback lifecycle.
    """
    now = _utcnow()

    stale = (
        Prescription.query
        .filter(
            Prescription.status
            == PrescriptionStatus.ACTIVE,
            Prescription.expires_at.isnot(None),
            Prescription.expires_at <= now,
        )
        .with_for_update()
        .all()
    )

    for prescription in stale:
        old_status = prescription.status.value

        prescription.status = (
            PrescriptionStatus.EXPIRED
        )

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Prescription",
            entity_id=prescription.id,
            description="Prescription expired (automated)",
            old_value={
                "status": old_status,
            },
            new_value={
                "status": prescription.status.value,
            },
        )

    db.session.flush()

    return len(stale)