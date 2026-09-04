"""
HIE (Health Information Exchange) submission service — Malaffi/NABIDH.

THIS IS UNRELATED TO app/modules/reports/services/reports_service.py.
reports_service.py = internal admin exports (CSV/XLSX for hospital staff).
This file = automatic clinical data submission to a UAE government HIE.

STATUS: Scaffold only. Resource-building functions are placeholders —
DO NOT fill in real FHIR resource shapes until Malaffi/NABIDH sandbox
access and their Implementation Guide are actually obtained. Building
this blind risks encoding wrong assumptions about their specific
profiles (which fields are required, which terminology bindings apply,
etc.) — guessing here is worse than leaving it unbuilt.
"""

from app.core.exceptions import ValidationError
from app.modules.patient.models.patient_model import Patient
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.prescription.models.prescription_model import Prescription


# ---------------------------------------------------------------------
# Resource builders — one per FHIR resource type.
# Each takes an internal model instance, returns a dict shaped like a
# FHIR resource. PLACEHOLDER bodies only — real field mappings come
# from Malaffi's Implementation Guide, not from generic FHIR spec.
# ---------------------------------------------------------------------

def build_patient_resource(patient: Patient) -> dict:
    if not patient.emirates_id:
        raise ValidationError(
            f"Patient {patient.id} has no Emirates ID — cannot submit to HIE"
        )
    # TODO: real shape per Malaffi's Patient profile, once IG is available.
    return {
        "resourceType": "Patient",
        "identifier": [
            {"system": "http://malaffi.ae/emirates-id", "value": patient.emirates_id},
        ],
        # ... gender, birthDate, name, etc. — placeholder, not final
    }


def build_encounter_resource(consultation: Consultation) -> dict:
    # TODO: real shape per Malaffi's Encounter profile.
    raise NotImplementedError("Encounter resource mapping not yet built — pending Malaffi IG access")


def build_condition_resource(consultation: Consultation) -> dict:
    if not consultation.icd10_code:
        raise ValidationError(
            f"Consultation {consultation.id} has no coded diagnosis — cannot submit as Condition"
        )
    # TODO: real shape per Malaffi's Condition profile.
    raise NotImplementedError("Condition resource mapping not yet built — pending Malaffi IG access")


def build_medication_request_resource(prescription: Prescription) -> dict:
    raise NotImplementedError("MedicationRequest resource mapping not yet built — pending Malaffi IG access")


# ---------------------------------------------------------------------
# Submission orchestration — decides WHAT gets sent WHEN.
# Not wired to any HTTP client yet — no Malaffi API base URL, no auth,
# no retry/backoff logic. All of that depends on sandbox credentials
# and the IG's stated submission pattern (real-time vs batch per
# clinical domain), which aren't available yet.
# ---------------------------------------------------------------------

def submit_patient(patient: Patient) -> dict:
    raise NotImplementedError(

    )