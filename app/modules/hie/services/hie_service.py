from datetime import datetime, timezone
from typing import Any, Optional

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.hie.models.hie_model import HIEIntegration, HIESubmission
from app.modules.hie.providers.malaffi_provider import (
    HIEProvider,
    MalaffiProvider,
)
from app.modules.patient.models.patient_model import Patient


# ======================================================================
# INTERNAL HELPERS
# ======================================================================


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_clinic(clinic_id: int) -> Clinic:
    """
    Return the clinic identified by clinic_id.

    Authorization to access the clinic should be enforced by the
    authenticated route/decorator layer. This helper only verifies
    that the clinic exists.
    """
    if clinic_id is None or clinic_id <= 0:
        raise ValidationError(
            "Invalid clinic ID"
        )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _get_patient(
    clinic_id: int,
    patient_id: Optional[int],
) -> Optional[Patient]:
    """
    Return a patient belonging to the supplied clinic.
    """
    if patient_id is None:
        return None

    if patient_id <= 0:
        raise ValidationError(
            "Invalid patient ID"
        )

    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong to the clinic"
        )

    return patient


def _get_integration(
    clinic_id: int,
    integration_id: Optional[int] = None,
) -> HIEIntegration:
    """
    Return an HIE integration belonging to the supplied clinic.

    If integration_id is omitted, return the active Malaffi
    integration for the clinic.
    """
    if clinic_id is None or clinic_id <= 0:
        raise ValidationError(
            "Invalid clinic ID"
        )

    if integration_id is not None:
        if integration_id <= 0:
            raise ValidationError(
                "Invalid HIE integration ID"
            )

        integration = db.session.get(
            HIEIntegration,
            integration_id,
        )

        if integration is None:
            raise NotFoundError(
                f"HIE integration {integration_id} not found"
            )

        if integration.clinic_id != clinic_id:
            raise ValidationError(
                "HIE integration does not belong to the clinic"
            )

        return integration

    integration = (
        HIEIntegration.query
        .filter(
            HIEIntegration.clinic_id == clinic_id,
            HIEIntegration.provider == "malaffi",
            HIEIntegration.status == HIEIntegrationStatus.ACTIVE,
        )
        .first()
    )

    if integration is None:
        raise ValidationError(
            "No active Malaffi integration is configured "
            "for this clinic"
        )

    return integration


def _validate_integration(
    integration: HIEIntegration,
) -> None:
    """
    Ensure the integration is configured for supported operation.
    """
    if integration is None:
        raise ValidationError(
            "HIE integration is required"
        )

    if integration.status != HIEIntegrationStatus.ACTIVE:
        raise ValidationError(
            "HIE integration is not active: "
            f"{integration.status.value}"
        )

    provider = (integration.provider or "").strip().lower()

    if not provider:
        raise ValidationError(
            "HIE integration provider is not configured"
        )

    if provider != "malaffi":
        raise ValidationError(
            f"Unsupported HIE provider: {integration.provider}"
        )


def _get_provider(
    integration: HIEIntegration,
) -> HIEProvider:
    """
    Resolve the provider implementation for an integration.
    """
    provider_name = (
        integration.provider or ""
    ).strip().lower()

    if provider_name == "malaffi":
        return MalaffiProvider(
            endpoint=integration.endpoint_url,
        )

    raise ValidationError(
        f"Unsupported HIE provider: "
        f"{integration.provider}"
    )


def _validate_patient_identifier(
    patient_identifier: str,
) -> str:
    """
    Normalize and validate an external HIE patient identifier.
    """
    if patient_identifier is None:
        raise ValidationError(
            "Patient identifier is required"
        )

    patient_identifier = patient_identifier.strip()

    if not patient_identifier:
        raise ValidationError(
            "Patient identifier is required"
        )

    return patient_identifier


def _validate_submission_context(
    *,
    integration: HIEIntegration,
    clinic_id: int,
    patient_id: Optional[int],
) -> None:
    """
    Ensure the integration and patient belong to the same clinic
    before creating a submission.
    """
    if integration is None:
        raise ValidationError(
            "HIE integration is required"
        )

    if integration.clinic_id != clinic_id:
        raise ValidationError(
            "HIE integration does not belong to the clinic"
        )

    if patient_id is not None:
        patient = db.session.get(
            Patient,
            patient_id,
        )

        if patient is None:
            raise NotFoundError(
                f"Patient {patient_id} not found"
            )

        if patient.clinic_id != clinic_id:
            raise ValidationError(
                "Patient does not belong to the clinic"
            )


# ======================================================================
# SUBMISSION HELPERS
# ======================================================================


@transactional
def _create_submission(
    *,
    integration_id: int,
    clinic_id: int,
    patient_id: Optional[int],
    operation: HIEOperation,
    request_data: Optional[dict[str, Any]],
) -> int:
    """
    Create a pending HIE submission after validating its ownership
    relationships.
    """
    if clinic_id <= 0:
        raise ValidationError(
            "Invalid clinic ID"
        )

    if integration_id <= 0:
        raise ValidationError(
            "Invalid HIE integration ID"
        )

    integration = db.session.get(
        HIEIntegration,
        integration_id,
    )

    if integration is None:
        raise NotFoundError(
            f"HIE integration {integration_id} not found"
        )

    _validate_submission_context(
        integration=integration,
        clinic_id=clinic_id,
        patient_id=patient_id,
    )

    if not isinstance(operation, HIEOperation):
        raise ValidationError(
            "Invalid HIE operation"
        )

    if request_data is not None and not isinstance(
        request_data,
        dict,
    ):
        raise ValidationError(
            "HIE request data must be an object"
        )

    submission = HIESubmission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=operation,
        status=HIESubmissionStatus.PENDING,
        request_data=request_data,
        retry_count=0,
    )

    db.session.add(submission)
    db.session.flush()

    return submission.id


@transactional
def _mark_submission_success(
    submission_id: int,
    response: dict[str, Any],
) -> None:
    """
    Mark an HIE submission as successful and persist the provider
    response metadata.
    """
    if submission_id <= 0:
        raise ValidationError(
            "Invalid HIE submission ID"
        )

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    if submission is None:
        raise NotFoundError(
            f"HIE submission {submission_id} not found"
        )

    if not isinstance(response, dict):
        raise ValidationError(
            "HIE provider response must be an object"
        )

    submission.status = HIESubmissionStatus.SUCCESS
    submission.response_data = response
    submission.status_code = response.get(
        "status_code"
    )
    submission.external_reference = response.get(
        "external_reference"
    )
    submission.error_message = None
    submission.submitted_at = _utcnow()


@transactional
def _mark_submission_failure(
    submission_id: int,
    error: Exception,
) -> None:
    """
    Mark an HIE submission as failed and increment its retry count.
    """
    if submission_id <= 0:
        raise ValidationError(
            "Invalid HIE submission ID"
        )

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    if submission is None:
        raise NotFoundError(
            f"HIE submission {submission_id} not found"
        )

    submission.status = HIESubmissionStatus.FAILED
    submission.error_message = str(error)
    submission.retry_count = (
        submission.retry_count or 0
    ) + 1
    submission.submitted_at = _utcnow()


@transactional
def _update_last_sync(
    integration_id: int,
) -> None:
    """
    Update the last successful HIE synchronization timestamp.
    """
    if integration_id <= 0:
        raise ValidationError(
            "Invalid HIE integration ID"
        )

    integration = db.session.get(
        HIEIntegration,
        integration_id,
    )

    if integration is None:
        raise NotFoundError(
            f"HIE integration {integration_id} not found"
        )

    integration.last_sync_at = _utcnow()


# ======================================================================
# HIE SUBMISSION OPERATIONS
# ======================================================================


def submit_patient(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit patient information to the configured HIE provider.
    """
    _get_clinic(clinic_id)

    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(
        integration
    )

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.PATIENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(
        integration
    )

    try:
        response = provider.submit_patient(
            payload
        )

    except Exception as exc:
        _mark_submission_failure(
            submission_id,
            exc,
        )
        raise

    _mark_submission_success(
        submission_id,
        response,
    )

    _update_last_sync(
        integration.id
    )

    return response


def submit_clinical_data(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit clinical data to the configured HIE provider.
    """
    _get_clinic(clinic_id)

    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(
        integration
    )

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(
        integration
    )

    try:
        response = provider.submit_clinical_data(
            payload
        )

    except Exception as exc:
        _mark_submission_failure(
            submission_id,
            exc,
        )
        raise

    _mark_submission_success(
        submission_id,
        response,
    )

    _update_last_sync(
        integration.id
    )

    return response


def submit_clinical_document(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit a clinical document to the configured HIE provider.
    """
    _get_clinic(clinic_id)

    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(
        integration
    )

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.CLINICAL_DOCUMENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(
        integration
    )

    try:
        response = provider.submit_clinical_document(
            payload
        )

    except Exception as exc:
        _mark_submission_failure(
            submission_id,
            exc,
        )
        raise

    _mark_submission_success(
        submission_id,
        response,
    )

    _update_last_sync(
        integration.id
    )

    return response


# ======================================================================
# HIE QUERY OPERATIONS
# ======================================================================


def query_patient(
    *,
    clinic_id: int,
    patient_identifier: str,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Query a patient from the configured HIE provider.
    """
    _get_clinic(clinic_id)

    patient_identifier = _validate_patient_identifier(
        patient_identifier
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(
        integration
    )

    provider = _get_provider(
        integration
    )

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=None,
        operation=HIEOperation.PATIENT_QUERY,
        request_data={
            "patient_identifier": patient_identifier,
        },
    )

    try:
        response = provider.query_patient(
            patient_identifier
        )

    except Exception as exc:
        _mark_submission_failure(
            submission_id,
            exc,
        )
        raise

    _mark_submission_success(
        submission_id,
        response,
    )

    _update_last_sync(
        integration.id
    )

    return response


def query_clinical_data(
    *,
    clinic_id: int,
    patient_identifier: str,
    filters: Optional[dict[str, Any]] = None,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Query clinical data from the configured HIE provider.
    """
    _get_clinic(clinic_id)

    patient_identifier = _validate_patient_identifier(
        patient_identifier
    )

    if filters is not None and not isinstance(
        filters,
        dict,
    ):
        raise ValidationError(
            "Clinical data filters must be an object"
        )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(
        integration
    )

    provider = _get_provider(
        integration
    )

    request_data = {
        "patient_identifier": patient_identifier,
        "filters": filters,
    }

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=None,
        operation=HIEOperation.CLINICAL_DATA_QUERY,
        request_data=request_data,
    )

    try:
        response = provider.query_clinical_data(
            patient_identifier,
            filters,
        )

    except Exception as exc:
        _mark_submission_failure(
            submission_id,
            exc,
        )
        raise

    _mark_submission_success(
        submission_id,
        response,
    )

    _update_last_sync(
        integration.id
    )

    return response


# ======================================================================
# HIE INTEGRATION MANAGEMENT
# ======================================================================


def get_hie_integration(
    clinic_id: int,
    integration_id: int,
) -> HIEIntegration:
    """
    Return an HIE integration belonging to the clinic.
    """
    _get_clinic(clinic_id)

    return _get_integration(
        clinic_id,
        integration_id,
    )


@transactional
def create_hie_integration(
    *,
    clinic_id: int,
    provider: str = "malaffi",
    endpoint_url: Optional[str] = None,
    organization_id: Optional[str] = None,
    facility_id: Optional[str] = None,
) -> HIEIntegration:
    """
    Create a pending HIE integration for a clinic.

    The clinic must already be authorized by the calling route.
    """
    _get_clinic(clinic_id)

    if provider is None:
        raise ValidationError(
            "Provider is required"
        )

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
        )

    if provider != "malaffi":
        raise ValidationError(
            f"Unsupported HIE provider: {provider}"
        )

    if endpoint_url is not None:
        endpoint_url = str(
            endpoint_url
        ).strip()

        if not endpoint_url:
            endpoint_url = None

    if organization_id is not None:
        organization_id = organization_id.strip()

        if not organization_id:
            raise ValidationError(
                "Organization ID cannot be empty"
            )

    if facility_id is not None:
        facility_id = facility_id.strip()

        if not facility_id:
            raise ValidationError(
                "Facility ID cannot be empty"
            )

    integration = HIEIntegration(
        clinic_id=clinic_id,
        provider=provider,
        status=HIEIntegrationStatus.PENDING,
        endpoint_url=endpoint_url,
        organization_id=organization_id,
        facility_id=facility_id,
    )

    db.session.add(integration)
    db.session.flush()

    return integration


@transactional
def update_hie_integration(
    *,
    clinic_id: int,
    integration_id: int,
    provider: Optional[str] = None,
    status: Optional[HIEIntegrationStatus] = None,
    endpoint_url: Optional[str] = None,
    organization_id: Optional[str] = None,
    facility_id: Optional[str] = None,
) -> HIEIntegration:
    """
    Update an HIE integration belonging to the clinic.
    """
    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    if provider is not None:
        provider = provider.strip().lower()

        if not provider:
            raise ValidationError(
                "Provider cannot be empty"
            )

        if provider != "malaffi":
            raise ValidationError(
                f"Unsupported HIE provider: {provider}"
            )

        integration.provider = provider

    if status is not None:
        if not isinstance(
            status,
            HIEIntegrationStatus,
        ):
            raise ValidationError(
                "Invalid HIE integration status"
            )

        integration.status = status

    if endpoint_url is not None:
        endpoint_url = str(
            endpoint_url
        ).strip()

        if not endpoint_url:
            raise ValidationError(
                "Endpoint URL cannot be empty"
            )

        integration.endpoint_url = endpoint_url

    if organization_id is not None:
        organization_id = organization_id.strip()

        if not organization_id:
            raise ValidationError(
                "Organization ID cannot be empty"
            )

        integration.organization_id = organization_id

    if facility_id is not None:
        facility_id = facility_id.strip()

        if not facility_id:
            raise ValidationError(
                "Facility ID cannot be empty"
            )

        integration.facility_id = facility_id

    return integration


# ======================================================================
# HIE SUBMISSION LISTING
# ======================================================================


def list_hie_submissions(
    *,
    clinic_id: int,
    integration_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    operation: Optional[HIEOperation] = None,
    status: Optional[HIESubmissionStatus] = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    List HIE submissions belonging exclusively to the supplied clinic.
    """
    _get_clinic(clinic_id)

    if page < 1:
        raise ValidationError(
            "Page must be greater than or equal to 1"
        )

    if per_page < 1 or per_page > 100:
        raise ValidationError(
            "per_page must be between 1 and 100"
        )

    if integration_id is not None:
        if integration_id <= 0:
            raise ValidationError(
                "Invalid HIE integration ID"
            )

        # Verify ownership before applying the filter.
        _get_integration(
            clinic_id,
            integration_id,
        )

    if patient_id is not None:
        if patient_id <= 0:
            raise ValidationError(
                "Invalid patient ID"
            )

        # Verify patient belongs to this clinic.
        _get_patient(
            clinic_id,
            patient_id,
        )

    if operation is not None and not isinstance(
        operation,
        HIEOperation,
    ):
        raise ValidationError(
            "Invalid HIE operation"
        )

    if status is not None and not isinstance(
        status,
        HIESubmissionStatus,
    ):
        raise ValidationError(
            "Invalid HIE submission status"
        )

    query = HIESubmission.query.filter(
        HIESubmission.clinic_id == clinic_id
    )

    if integration_id is not None:
        query = query.filter(
            HIESubmission.integration_id == integration_id
        )

    if patient_id is not None:
        query = query.filter(
            HIESubmission.patient_id == patient_id
        )

    if operation is not None:
        query = query.filter(
            HIESubmission.operation == operation
        )

    if status is not None:
        query = query.filter(
            HIESubmission.status == status
        )

    return (
        query
        .order_by(
            HIESubmission.created_at.desc()
        )
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
    )