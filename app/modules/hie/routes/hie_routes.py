from flask import Blueprint, jsonify, request

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

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


@hie_bp.post("/integrations")
@role_required(*HIE_ADMIN_ROLES)
def create_integration():
    payload = HIEIntegrationCreateSchema.model_validate(
        request.get_json(silent=True) or {}
    )

    integration = create_hie_integration(
        clinic_id=payload.clinic_id,
        provider=payload.provider,
        endpoint_url=payload.endpoint_url,
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
    clinic_id = request.args.get(
        "clinic_id",
        type=int,
    )

    if not clinic_id:
        return jsonify(
            {
                "success": False,
                "error": "clinic_id query parameter is required",
            }
        ), 400

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
    payload_data = request.get_json(silent=True) or {}

    payload = HIEIntegrationUpdateSchema.model_validate(
        payload_data
    )

    clinic_id = payload_data.get("clinic_id")

    if not clinic_id:
        clinic_id = request.args.get(
            "clinic_id",
            type=int,
        )

    if not clinic_id:
        return jsonify(
            {
                "success": False,
                "error": "clinic_id is required",
            }
        ), 400

    integration = update_hie_integration(
        clinic_id=clinic_id,
        integration_id=integration_id,
        provider=payload.provider,
        status=payload.status,
        endpoint_url=payload.endpoint_url,
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


@hie_bp.get("/submissions")
@role_required(*HIE_VIEW_ROLES)
def get_submissions():
    payload = HIESubmissionQuerySchema.model_validate(
        request.args.to_dict()
    )

    if payload.clinic_id is None:
        return jsonify(
            {
                "success": False,
                "error": "clinic_id query parameter is required",
            }
        ), 400

    pagination = list_hie_submissions(
        clinic_id=payload.clinic_id,
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