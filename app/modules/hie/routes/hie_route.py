from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import role_required
from app.extensions import db
from app.core.auth.user.models.user_model import User

from app.modules.hie.schemas.hie_schema import (
    HIEIntegrationCreateSchema,
    HIEIntegrationResponseSchema,
    HIEIntegrationUpdateSchema,
    HIESubmissionListResponseSchema,
    HIESubmissionQuerySchema,
    HIESubmissionResponseSchema,
)
from app.modules.hie.services.hie_service import (
    create_hie_integration,
    get_hie_integration,
    list_hie_submissions,
    update_hie_integration,
)


hie_bp = Blueprint(
    "hie",
    __name__,
    url_prefix="/api/hie",
)


HIE_ADMIN_ROLES = (
    Role.ADMIN,
)


HIE_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.LAB_TECHNICIAN,
    Role.PHARMACIST,
)


# ======================================================================
# AUTHENTICATED CLINIC CONTEXT
# ======================================================================


def _get_current_user() -> User:
    """
    Resolve the authenticated active user from the JWT.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _get_current_clinic_id() -> int:
    """
    Resolve the clinic associated with the authenticated user.

    clinic_id is intentionally NOT accepted from request body or query
    parameters because it is a tenant/security boundary.
    """
    user = _get_current_user()

    clinic_id = getattr(
        user,
        "clinic_id",
        None,
    )

    if clinic_id is None or clinic_id <= 0:
        raise ValidationError(
            "Authenticated user is not associated with a clinic"
        )

    return clinic_id


# ======================================================================
# HIE INTEGRATIONS
# ======================================================================


@hie_bp.post("/integrations")
@role_required(*HIE_ADMIN_ROLES)
def create_integration():
    """
    Create an HIE integration for the authenticated user's clinic.
    """
    payload = HIEIntegrationCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    clinic_id = _get_current_clinic_id()

    integration = create_hie_integration(
        clinic_id=clinic_id,
        provider=payload.provider,
        endpoint_url=(
            str(payload.endpoint_url)
            if payload.endpoint_url is not None
            else None
        ),
        organization_id=payload.organization_id,
        facility_id=payload.facility_id,
    )

    response = HIEIntegrationResponseSchema.model_validate(
        integration
    )

    return jsonify(
        {
            "success": True,
            "data": response.model_dump(mode="json"),
        }
    ), 201


@hie_bp.get("/integrations/<int:integration_id>")
@role_required(*HIE_VIEW_ROLES)
def get_integration(integration_id: int):
    """
    Retrieve an HIE integration belonging to the authenticated
    user's clinic.
    """
    clinic_id = _get_current_clinic_id()

    integration = get_hie_integration(
        clinic_id=clinic_id,
        integration_id=integration_id,
    )

    response = HIEIntegrationResponseSchema.model_validate(
        integration
    )

    return jsonify(
        {
            "success": True,
            "data": response.model_dump(mode="json"),
        }
    ), 200


@hie_bp.patch("/integrations/<int:integration_id>")
@role_required(*HIE_ADMIN_ROLES)
def update_integration(integration_id: int):
    """
    Update an HIE integration belonging to the authenticated
    user's clinic.
    """
    payload = HIEIntegrationUpdateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    clinic_id = _get_current_clinic_id()

    integration = update_hie_integration(
        clinic_id=clinic_id,
        integration_id=integration_id,
        provider=payload.provider,
        status=payload.status,
        endpoint_url=(
            str(payload.endpoint_url)
            if payload.endpoint_url is not None
            else None
        ),
        organization_id=payload.organization_id,
        facility_id=payload.facility_id,
    )

    response = HIEIntegrationResponseSchema.model_validate(
        integration
    )

    return jsonify(
        {
            "success": True,
            "data": response.model_dump(mode="json"),
        }
    ), 200


# ======================================================================
# HIE SUBMISSIONS
# ======================================================================


@hie_bp.get("/submissions")
@role_required(*HIE_VIEW_ROLES)
def get_submissions():
    """
    List HIE submissions belonging exclusively to the authenticated
    user's clinic.
    """
    payload = HIESubmissionQuerySchema.model_validate(
        request.args.to_dict()
    )

    clinic_id = _get_current_clinic_id()

    pagination = list_hie_submissions(
        clinic_id=clinic_id,
        integration_id=payload.integration_id,
        patient_id=payload.patient_id,
        operation=payload.operation,
        status=payload.status,
        page=payload.page,
        per_page=payload.per_page,
    )

    response = HIESubmissionListResponseSchema(
        items=[
            HIESubmissionResponseSchema.model_validate(
                submission
            )
            for submission in pagination.items
        ],
        total=pagination.total,
        page=pagination.page,
        per_page=pagination.per_page,
    )

    return jsonify(
        {
            "success": True,
            "data": response.model_dump(mode="json"),
        }
    ), 200