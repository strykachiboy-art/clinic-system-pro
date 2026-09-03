from datetime import datetime, timedelta, timezone
from itertools import combinations
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.prescription_enums import PrescriptionStatus, DrugInteractionSeverity
from app.modules.prescription.models.prescription_model import Prescription, PrescriptionItem, DrugInteraction
from app.modules.pharmacy.services.pharmacy_service import get_drug


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Interaction lookups — order-independent by design
# ---------------------------------------------------------------------

def _find_interaction(drug_a_id: int, drug_b_id: int) -> DrugInteraction | None:
    """
    Checks both (a,b) and (b,a) — DrugInteraction rows aren't stored in
    a canonical order, so a naive single-direction query would silently
    miss half of them depending on which order the pair was originally
    entered in.
    """
    return DrugInteraction.query.filter(
        db.or_(
            db.and_(DrugInteraction.drug_a_id == drug_a_id, DrugInteraction.drug_b_id == drug_b_id),
            db.and_(DrugInteraction.drug_a_id == drug_b_id, DrugInteraction.drug_b_id == drug_a_id),
        )
    ).first()


@transactional
def create_drug_interaction(drug_a_id: int, drug_b_id: int, severity: DrugInteractionSeverity,
                             description: str | None = None) -> DrugInteraction:
    if drug_a_id == drug_b_id:
        raise ValidationError("A drug cannot interact with itself")

    get_drug(drug_a_id)
    get_drug(drug_b_id)

    if _find_interaction(drug_a_id, drug_b_id):
        raise ConflictError(f"An interaction between drugs {drug_a_id} and {drug_b_id} already exists")

    a, b = sorted((drug_a_id, drug_b_id))

    interaction = DrugInteraction(drug_a_id=a, drug_b_id=b, severity=severity, description=description)
    db.session.add(interaction)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="DrugInteraction",
        entity_id=interaction.id,
        description=f"Drug interaction added: {a} x {b} ({severity.value})",
        new_value={"severity": severity.value},
    )
    return interaction


def check_interactions(drug_ids: list[int]) -> list[dict]:
    """
    Checks every pairwise combination in a list of drugs (e.g. a
    prescription's full drug list) against the DB interaction table.
    """
    found = []
    for drug_a_id, drug_b_id in combinations(sorted(set(drug_ids)), 2):
        interaction = _find_interaction(drug_a_id, drug_b_id)
        if interaction:
            found.append({
                "drug_a_id": interaction.drug_a_id,
                "drug_b_id": interaction.drug_b_id,
                "severity": interaction.severity.value,
                "description": interaction.description,
            })
    return found


# ---------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------

def get_prescription(prescription_id: int) -> Prescription:
    prescription = Prescription.query.get(prescription_id)
    if prescription is None:
        raise NotFoundError(f"Prescription {prescription_id} not found")
    return prescription


def list_prescriptions_for_patient(patient_id: int, active_only: bool = False) -> list[Prescription]:
    query = Prescription.query.filter_by(patient_id=patient_id)
    if active_only:
        query = query.filter_by(status=PrescriptionStatus.ACTIVE)
    return query.order_by(Prescription.issued_at.desc()).all()


@transactional
def create_prescription(clinic_id: int, patient_id: int, prescribed_by_id: int,
                         items: list[dict], consultation_id: int | None = None,
                         expires_at=None, notes: str | None = None) -> tuple[Prescription, list[dict]]:
    """
    items = [{'drug_id': int, 'dosage': str, 'frequency': str,
              'duration': str, 'quantity': int, 'instructions': str}, ...]
    Returns (prescription, interaction_warnings) — interactions are
    NEVER used to block creation.
    """
    if not items:
        raise ValidationError("A prescription must include at least one item")

    drug_ids = []
    for entry in items:
        get_drug(entry["drug_id"])  # 404s if any drug doesn't exist
        drug_ids.append(entry["drug_id"])

    prescription = Prescription(
        clinic_id=clinic_id,
        patient_id=patient_id,
        consultation_id=consultation_id,
        prescribed_by_id=prescribed_by_id,
        status=PrescriptionStatus.ACTIVE,
        notes=notes,
        expires_at=expires_at,
    )
    db.session.add(prescription)
    db.session.flush()

    for entry in items:
        db.session.add(PrescriptionItem(
            prescription_id=prescription.id,
            drug_id=entry["drug_id"],
            dosage=entry.get("dosage"),
            frequency=entry.get("frequency"),
            duration=entry.get("duration"),
            quantity=entry.get("quantity"),
            instructions=entry.get("instructions"),
        ))

    warnings = check_interactions(drug_ids)

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description=f"Prescription created for patient {patient_id} ({len(items)} item(s))"
        + (f" — {len(warnings)} interaction warning(s)" if warnings else ""),
        new_value={"drug_ids": drug_ids, "interaction_warnings": warnings},
    )
    return prescription, warnings


def _assert_status(prescription: Prescription, *allowed: PrescriptionStatus):
    if prescription.status not in allowed:
        raise ConflictError(
            f"Prescription {prescription.id} is '{prescription.status.value}', "
            f"expected one of {[s.value for s in allowed]}"
        )


@transactional
def cancel_prescription(prescription_id: int, reason: str | None = None) -> Prescription:
    prescription = get_prescription(prescription_id)
    _assert_status(prescription, PrescriptionStatus.ACTIVE)

    old_status = prescription.status.value
    prescription.status = PrescriptionStatus.CANCELLED
    if reason:
        prescription.notes = f"{prescription.notes or ''}\nCancelled: {reason}".strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description="Prescription cancelled" + (f": {reason}" if reason else ""),
        old_value={"status": old_status},
        new_value={"status": prescription.status.value},
    )
    return prescription


@transactional
def complete_prescription(prescription_id: int) -> Prescription:
    """Marks a prescription as fully fulfilled — call this once dispensing is done."""
    prescription = get_prescription(prescription_id)
    _assert_status(prescription, PrescriptionStatus.ACTIVE)

    old_status = prescription.status.value
    prescription.status = PrescriptionStatus.COMPLETED

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Prescription",
        entity_id=prescription.id,
        description="Prescription marked completed",
        old_value={"status": old_status},
        new_value={"status": prescription.status.value},
    )
    return prescription


def expire_stale_prescriptions() -> int:
    """
    Run periodically via Celery beat (same pattern as
    billing_service.mark_overdue_invoices). Not decorated
    @transactional since it does its own bulk update + single commit,
    matching the existing Celery task convention in this codebase.
    """
    now = _utcnow()
    stale = Prescription.query.filter(
        Prescription.status == PrescriptionStatus.ACTIVE,
        Prescription.expires_at.isnot(None),
        Prescription.expires_at < now,
    ).all()

    for prescription in stale:
        prescription.status = PrescriptionStatus.EXPIRED
        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Prescription",
            entity_id=prescription.id,
            description="Prescription expired (automated)",
            new_value={"status": "expired"},
        )

    db.session.commit()
    return len(stale)