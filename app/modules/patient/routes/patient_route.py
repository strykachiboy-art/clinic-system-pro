from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.patient.schemas.patient_schema import (
    PatientCreateSchema,
    PatientFamilyMemberCreateSchema,
    PatientFamilyMemberUpdateSchema,
    PatientInsuranceCreateSchema,
    PatientInsuranceUpdateSchema,
    PatientStatusUpdateSchema,
    PatientUpdateSchema,
    PatientVitalsCreateSchema,
    PatientResponseSchema,
    PatientFamilyMemberResponseSchema,
    PatientInsuranceResponseSchema,
    PatientVitalsResponseSchema,
)

from app.modules.patient.services.patient_service import (
    add_family_member,
    add_insurance,
    create_patient,
    get_latest_vitals,
    get_patient,
    get_vitals_history,
    list_family_members,
    list_insurances,
    list_patients,
    record_vitals,
    remove_family_member,
    set_active_status,
    update_family_member,
    update_insurance,
    update_patient,
)


patient_bp = Blueprint(
    "patients",
    __name__,
    url_prefix="/api/patients",
)


# ============================================================================
# Patient
# ============================================================================

@patient_bp.route("", methods=["POST"])
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def create_patient_route():
    data = PatientCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    clinic_id = int(get_jwt_identity())

    patient = create_patient(
        clinic_id=clinic_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientResponseSchema.model_validate(patient).model_dump(
            mode="json"
        ),
    }), 201


@patient_bp.route("", methods=["GET"])
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.PARAMEDIC,
    Role.EMT,
)
def list_patients_route():
    clinic_id = request.args.get("clinic_id", type=int)

    active_only = (
        request.args.get(
            "active_only",
            "false",
        ).lower()
        == "true"
    )

    search = request.args.get("search")

    patients = list_patients(
        clinic_id=clinic_id,
        active_only=active_only,
        search=search,
    )

    return jsonify({
        "success": True,
        "data": [
            PatientResponseSchema.model_validate(patient).model_dump(
                mode="json"
            )
            for patient in patients
        ],
    }), 200


@patient_bp.route("/<int:patient_id>", methods=["GET"])
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.PARAMEDIC,
    Role.EMT,
)
def get_patient_route(patient_id: int):
    patient = get_patient(patient_id)

    return jsonify({
        "success": True,
        "data": PatientResponseSchema.model_validate(patient).model_dump(
            mode="json"
        ),
    }), 200


@patient_bp.route("/<int:patient_id>", methods=["PATCH"])
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def update_patient_route(patient_id: int):
    data = PatientUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    patient = update_patient(
        patient_id=patient_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientResponseSchema.model_validate(patient).model_dump(
            mode="json"
        ),
    }), 200


@patient_bp.route("/<int:patient_id>/status", methods=["PATCH"])
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def set_patient_status_route(patient_id: int):
    data = PatientStatusUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    patient = set_active_status(
        patient_id=patient_id,
        is_active=data.is_active,
    )

    return jsonify({
        "success": True,
        "data": PatientResponseSchema.model_validate(patient).model_dump(
            mode="json"
        ),
    }), 200


# ============================================================================
# Family Members
# ============================================================================

@patient_bp.route(
    "/<int:patient_id>/family",
    methods=["GET"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
)
def list_family_members_route(patient_id: int):
    members = list_family_members(patient_id)

    return jsonify({
        "success": True,
        "data": [
            PatientFamilyMemberResponseSchema
            .model_validate(member)
            .model_dump(mode="json")
            for member in members
        ],
    }), 200


@patient_bp.route(
    "/<int:patient_id>/family",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def add_family_member_route(patient_id: int):
    data = PatientFamilyMemberCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    member = add_family_member(
        patient_id=patient_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientFamilyMemberResponseSchema
        .model_validate(member)
        .model_dump(mode="json"),
    }), 201


@patient_bp.route(
    "/<int:patient_id>/family/<int:family_member_id>",
    methods=["PATCH"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def update_family_member_route(
    patient_id: int,
    family_member_id: int,
):
    data = PatientFamilyMemberUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    member = update_family_member(
        patient_id=patient_id,
        family_member_id=family_member_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientFamilyMemberResponseSchema
        .model_validate(member)
        .model_dump(mode="json"),
    }), 200


@patient_bp.route(
    "/<int:patient_id>/family/<int:family_member_id>",
    methods=["DELETE"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def remove_family_member_route(
    patient_id: int,
    family_member_id: int,
):
    remove_family_member(
        patient_id=patient_id,
        family_member_id=family_member_id,
    )

    return jsonify({
        "success": True,
        "message": "Family member removed successfully",
    }), 200


# ============================================================================
# Insurance
# ============================================================================

@patient_bp.route(
    "/<int:patient_id>/insurance",
    methods=["GET"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
    Role.ACCOUNTANT,
)
def list_insurances_route(patient_id: int):
    insurances = list_insurances(patient_id)

    return jsonify({
        "success": True,
        "data": [
            PatientInsuranceResponseSchema
            .model_validate(insurance)
            .model_dump(mode="json")
            for insurance in insurances
        ],
    }), 200


@patient_bp.route(
    "/<int:patient_id>/insurance",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def add_insurance_route(patient_id: int):
    data = PatientInsuranceCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    insurance = add_insurance(
        patient_id=patient_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientInsuranceResponseSchema
        .model_validate(insurance)
        .model_dump(mode="json"),
    }), 201


@patient_bp.route(
    "/<int:patient_id>/insurance/<int:insurance_id>",
    methods=["PATCH"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def update_insurance_route(
    patient_id: int,
    insurance_id: int,
):
    data = PatientInsuranceUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    insurance = update_insurance(
        patient_id=patient_id,
        insurance_id=insurance_id,
        data=data.model_dump(exclude_unset=True),
    )

    return jsonify({
        "success": True,
        "data": PatientInsuranceResponseSchema
        .model_validate(insurance)
        .model_dump(mode="json"),
    }), 200


# ============================================================================
# Vitals
# ============================================================================

@patient_bp.route(
    "/<int:patient_id>/vitals",
    methods=["GET"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)
def get_vitals_history_route(patient_id: int):
    vitals = get_vitals_history(patient_id)

    return jsonify({
        "success": True,
        "data": [
            PatientVitalsResponseSchema
            .model_validate(record)
            .model_dump(mode="json")
            for record in vitals
        ],
    }), 200


@patient_bp.route(
    "/<int:patient_id>/vitals/latest",
    methods=["GET"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)
def get_latest_vitals_route(patient_id: int):
    vitals = get_latest_vitals(patient_id)

    if vitals is None:
        return jsonify({
            "success": True,
            "data": None,
        }), 200

    return jsonify({
        "success": True,
        "data": PatientVitalsResponseSchema
        .model_validate(vitals)
        .model_dump(mode="json"),
    }), 200


@patient_bp.route(
    "/<int:patient_id>/vitals",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)
def record_vitals_route(patient_id: int):
    data = PatientVitalsCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    payload = data.model_dump(
        exclude_unset=True,
    )

    consultation_id = payload.pop(
        "consultation_id",
        None,
    )

    recorded_by_id = payload.pop(
        "recorded_by_id",
        None,
    )

    vitals = record_vitals(
        patient_id=patient_id,
        data=payload,
        consultation_id=consultation_id,
        recorded_by_id=recorded_by_id,
    )

    return jsonify({
        "success": True,
        "data": PatientVitalsResponseSchema
        .model_validate(vitals)
        .model_dump(mode="json"),
    }), 201