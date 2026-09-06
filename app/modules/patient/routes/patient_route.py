from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db
from app.core.auth.user.models.user_model import User
from app.core.exceptions import DomainError, ValidationError
from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.patient.models.patient_model import Patient

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
# Helpers
# ============================================================================

def _get_current_user() -> User:
    """
    Load the authenticated user from the JWT identity.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(User, user_id)

    if user is None:
        raise ValidationError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    return user


def _get_current_clinic_id() -> int:
    """
    Return the clinic belonging to the authenticated user.

    Patient data is clinic-scoped, so routes must never trust
    clinic_id supplied by the client.
    """
    user = _get_current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not assigned to a clinic"
        )

    return user.clinic_id


def _get_patient_in_current_clinic(
    patient_id: int,
) -> Patient:
    """
    Load a patient and ensure the patient belongs to the
    authenticated user's clinic.
    """
    clinic_id = _get_current_clinic_id()

    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise ValidationError(
            f"Patient {patient_id} not found"
        )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong to the authenticated user's clinic"
        )

    return patient


def _validate_payload(schema_class):
    """
    Validate a JSON request body using the supplied Pydantic schema.
    """
    payload = request.get_json(
        silent=True
    ) or {}

    try:
        return schema_class.model_validate(
            payload
        )
    except PydanticValidationError as exc:
        raise exc


def _validation_error_response(
    exc: PydanticValidationError,
):
    return jsonify(
        {
            "success": False,
            "error": "Validation failed",
            "details": exc.errors(),
        }
    ), 400


def _domain_error_response(
    exc: DomainError,
):
    return jsonify(
        {
            "success": False,
            "error": str(exc),
        }
    ), exc.status_code


# ============================================================================
# Patient
# ============================================================================

@patient_bp.route(
    "",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def create_patient_route():
    try:
        data = _validate_payload(
            PatientCreateSchema
        )

        clinic_id = _get_current_clinic_id()

        patient = create_patient(
            clinic_id=clinic_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientResponseSchema
                .model_validate(patient)
                .model_dump(mode="json"),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "",
    methods=["GET"],
)
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
    try:
        clinic_id = _get_current_clinic_id()

        active_only = (
            request.args.get(
                "active_only",
                "false",
            ).lower()
            == "true"
        )

        search = request.args.get(
            "search"
        )

        patients = list_patients(
            clinic_id=clinic_id,
            active_only=active_only,
            search=search,
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    PatientResponseSchema
                    .model_validate(patient)
                    .model_dump(mode="json")
                    for patient in patients
                ],
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>",
    methods=["GET"],
)
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
def get_patient_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        patient = get_patient(
            patient_id
        )

        return jsonify(
            {
                "success": True,
                "data": PatientResponseSchema
                .model_validate(patient)
                .model_dump(mode="json"),
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>",
    methods=["PATCH"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def update_patient_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientUpdateSchema
        )

        patient = update_patient(
            patient_id=patient_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientResponseSchema
                .model_validate(patient)
                .model_dump(mode="json"),
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>/status",
    methods=["PATCH"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def set_patient_status_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientStatusUpdateSchema
        )

        patient = set_active_status(
            patient_id=patient_id,
            is_active=data.is_active,
        )

        return jsonify(
            {
                "success": True,
                "data": PatientResponseSchema
                .model_validate(patient)
                .model_dump(mode="json"),
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


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
def list_family_members_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        members = list_family_members(
            patient_id
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    PatientFamilyMemberResponseSchema
                    .model_validate(member)
                    .model_dump(mode="json")
                    for member in members
                ],
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>/family",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def add_family_member_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientFamilyMemberCreateSchema
        )

        member = add_family_member(
            patient_id=patient_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientFamilyMemberResponseSchema
                .model_validate(member)
                .model_dump(mode="json"),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


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
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientFamilyMemberUpdateSchema
        )

        member = update_family_member(
            patient_id=patient_id,
            family_member_id=family_member_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientFamilyMemberResponseSchema
                .model_validate(member)
                .model_dump(mode="json"),
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


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
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        remove_family_member(
            patient_id=patient_id,
            family_member_id=family_member_id,
        )

        return jsonify(
            {
                "success": True,
                "message": (
                    "Family member removed successfully"
                ),
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


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
def list_insurances_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        insurances = list_insurances(
            patient_id
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    PatientInsuranceResponseSchema
                    .model_validate(insurance)
                    .model_dump(mode="json")
                    for insurance in insurances
                ],
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>/insurance",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.RECEPTIONIST,
)
def add_insurance_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientInsuranceCreateSchema
        )

        insurance = add_insurance(
            patient_id=patient_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientInsuranceResponseSchema
                .model_validate(insurance)
                .model_dump(mode="json"),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


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
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientInsuranceUpdateSchema
        )

        insurance = update_insurance(
            patient_id=patient_id,
            insurance_id=insurance_id,
            data=data.model_dump(
                exclude_unset=True
            ),
        )

        return jsonify(
            {
                "success": True,
                "data": PatientInsuranceResponseSchema
                .model_validate(insurance)
                .model_dump(mode="json"),
            }
        ), 200

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)


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
def get_vitals_history_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        vitals = get_vitals_history(
            patient_id
        )

        return jsonify(
            {
                "success": True,
                "data": [
                    PatientVitalsResponseSchema
                    .model_validate(record)
                    .model_dump(mode="json")
                    for record in vitals
                ],
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>/vitals/latest",
    methods=["GET"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)
def get_latest_vitals_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        vitals = get_latest_vitals(
            patient_id
        )

        if vitals is None:
            return jsonify(
                {
                    "success": True,
                    "data": None,
                }
            ), 200

        return jsonify(
            {
                "success": True,
                "data": PatientVitalsResponseSchema
                .model_validate(vitals)
                .model_dump(mode="json"),
            }
        ), 200

    except DomainError as exc:
        return _domain_error_response(exc)


@patient_bp.route(
    "/<int:patient_id>/vitals",
    methods=["POST"],
)
@role_required(
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
)
def record_vitals_route(
    patient_id: int,
):
    try:
        _get_patient_in_current_clinic(
            patient_id
        )

        data = _validate_payload(
            PatientVitalsCreateSchema
        )

        payload = data.model_dump(
            exclude_unset=True
        )

        consultation_id = payload.pop(
            "consultation_id",
            None,
        )

        # Do NOT trust recorded_by_id from the client.
        # The authenticated JWT identity is the recorder.
        _get_current_user()

        recorded_by_id = int(
            get_jwt_identity()
        )

        payload.pop(
            "recorded_by_id",
            None,
        )

        vitals = record_vitals(
            patient_id=patient_id,
            data=payload,
            consultation_id=consultation_id,
            recorded_by_id=recorded_by_id,
        )

        return jsonify(
            {
                "success": True,
                "data": PatientVitalsResponseSchema
                .model_validate(vitals)
                .model_dump(mode="json"),
            }
        ), 201

    except PydanticValidationError as exc:
        return _validation_error_response(exc)

    except DomainError as exc:
        return _domain_error_response(exc)