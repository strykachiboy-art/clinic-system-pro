from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required
from app.modules.prescription.schemas.prescription_schema import (
    DrugInteractionCheckSchema,
    DrugInteractionCreateSchema,
    PrescriptionCancelSchema,
    PrescriptionCreateSchema,
)
from app.modules.prescription.services.prescription_service import (
    cancel_prescription,
    check_interactions,
    complete_prescription,
    create_drug_interaction,
    create_prescription,
    get_prescription,
    list_prescriptions_for_patient,
)

prescription_bp = Blueprint(
    "prescription",
    __name__,
    url_prefix="/prescriptions",
)


PRESCRIPTION_VIEW_ROLES = (
    Role.DOCTOR,
    Role.PHARMACIST,
)

PRESCRIPTION_WRITE_ROLES = (
    Role.DOCTOR,
)

PRESCRIPTION_LIFECYCLE_ROLES = (
    Role.DOCTOR,
    Role.PHARMACIST,
)

DRUG_INTERACTION_MANAGEMENT_ROLES = (
    Role.ADMIN,
)


# =====================================================================
# Serializers
# =====================================================================

def _serialize_prescription_item(item):
    return {
        "id": item.id,
        "prescription_id": item.prescription_id,
        "drug_id": item.drug_id,
        "dosage": item.dosage,
        "frequency": item.frequency,
        "duration": item.duration,
        "quantity": item.quantity,
        "instructions": item.instructions,
    }


def _serialize_prescription(prescription):
    return {
        "id": prescription.id,
        "clinic_id": prescription.clinic_id,
        "patient_id": prescription.patient_id,
        "consultation_id": prescription.consultation_id,
        "prescribed_by_id": prescription.prescribed_by_id,
        "status": prescription.status.value,
        "notes": prescription.notes,
        "issued_at": (
            prescription.issued_at.isoformat()
            if prescription.issued_at
            else None
        ),
        "expires_at": (
            prescription.expires_at.isoformat()
            if prescription.expires_at
            else None
        ),
        "items": [
            _serialize_prescription_item(item)
            for item in prescription.items
        ],
    }


def _serialize_drug_interaction(interaction):
    return {
        "id": interaction.id,
        "drug_a_id": interaction.drug_a_id,
        "drug_b_id": interaction.drug_b_id,
        "severity": interaction.severity.value,
        "description": interaction.description,
    }


# =====================================================================
# Prescription Routes
# =====================================================================

@prescription_bp.post("")
@jwt_required()
@role_required(*PRESCRIPTION_WRITE_ROLES)
def create_prescription_route():
    payload = PrescriptionCreateSchema.model_validate(
        request.get_json() or {}
    )

    prescription, warnings = create_prescription(
        clinic_id=payload.clinic_id,
        patient_id=payload.patient_id,
        prescribed_by_id=payload.prescribed_by_id,
        items=[
            item.model_dump()
            for item in payload.items
        ],
        consultation_id=payload.consultation_id,
        expires_at=payload.expires_at,
        notes=payload.notes,
    )

    return jsonify(
        {
            "success": True,
            "message": "Prescription created successfully",
            "data": _serialize_prescription(prescription),
            "interaction_warnings": warnings,
        }
    ), 201


@prescription_bp.get("/<int:prescription_id>")
@jwt_required()
@role_required(*PRESCRIPTION_VIEW_ROLES)
def get_prescription_route(prescription_id: int):
    prescription = get_prescription(prescription_id)

    return jsonify(
        {
            "success": True,
            "data": _serialize_prescription(prescription),
        }
    ), 200


@prescription_bp.get("/patients/<int:patient_id>")
@jwt_required()
@role_required(*PRESCRIPTION_VIEW_ROLES)
def list_patient_prescriptions_route(patient_id: int):
    active_only = (
        request.args.get("active_only", "false").lower() == "true"
    )

    prescriptions = list_prescriptions_for_patient(
        patient_id=patient_id,
        active_only=active_only,
    )

    return jsonify(
        {
            "success": True,
            "data": [
                _serialize_prescription(prescription)
                for prescription in prescriptions
            ],
        }
    ), 200


@prescription_bp.post("/<int:prescription_id>/cancel")
@jwt_required()
@role_required(*PRESCRIPTION_WRITE_ROLES)
def cancel_prescription_route(prescription_id: int):
    payload = PrescriptionCancelSchema.model_validate(
        request.get_json() or {}
    )

    prescription = cancel_prescription(
        prescription_id=prescription_id,
        reason=payload.reason,
    )

    return jsonify(
        {
            "success": True,
            "message": "Prescription cancelled successfully",
            "data": _serialize_prescription(prescription),
        }
    ), 200


@prescription_bp.post("/<int:prescription_id>/complete")
@jwt_required()
@role_required(*PRESCRIPTION_LIFECYCLE_ROLES)
def complete_prescription_route(prescription_id: int):
    prescription = complete_prescription(
        prescription_id=prescription_id,
    )

    return jsonify(
        {
            "success": True,
            "message": "Prescription completed successfully",
            "data": _serialize_prescription(prescription),
        }
    ), 200


# =====================================================================
# Drug Interaction Routes
# =====================================================================

@prescription_bp.post("/interactions/check")
@jwt_required()
@role_required(*PRESCRIPTION_VIEW_ROLES)
def check_drug_interactions_route():
    payload = DrugInteractionCheckSchema.model_validate(
        request.get_json() or {}
    )

    interactions = check_interactions(
        drug_ids=payload.drug_ids,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "drug_ids": payload.drug_ids,
                "has_interactions": bool(interactions),
                "interaction_warnings": interactions,
            },
        }
    ), 200


@prescription_bp.post("/interactions")
@jwt_required()
@role_required(*DRUG_INTERACTION_MANAGEMENT_ROLES)
def create_drug_interaction_route():
    payload = DrugInteractionCreateSchema.model_validate(
        request.get_json() or {}
    )

    interaction = create_drug_interaction(
        drug_a_id=payload.drug_a_id,
        drug_b_id=payload.drug_b_id,
        severity=payload.severity,
        description=payload.description,
    )

    return jsonify(
        {
            "success": True,
            "message": "Drug interaction created successfully",
            "data": _serialize_drug_interaction(interaction),
        }
    ), 201