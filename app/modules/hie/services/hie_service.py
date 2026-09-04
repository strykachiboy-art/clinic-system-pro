from datetime import datetime, timezone
from typing import Any, Optional

from app.core.enums.hie_enums import HIEIntegrationStatus, HIEOperation
from app.core.exceptions import NotFoundError, ValidationError
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.hie.models.hie_model import HIEIntegration, HIESubmission
from app.modules.hie.providers.malaffi_provider import HIEProvider, MalaffiProvider
from app.modules.patient.models.patient_model import Patient
from app.modules.clinic.models.clinic_model import Clinic


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_clinic(clinic_id: int) -> Clinic:
    clinic = db.session.get(Clinic, clinic_id)

    if not clinic:
        raise NotFoundError(f"Clinic {clinic_id} not found")

    return clinic


def _get_patient(
    clinic_id: int,
    patient_id: Optional[int],
) -> Optional[Patient]:
    if patient_id is None:
        return None

    patient = db.session.get(Patient, patient_id)

    if not patient:
        raise NotFoundError(f"Patient {patient_id} not found")

    if patient.clinic_id != clinic_id:
        raise ValidationError(
            "Patient does not belong to the supplied clinic"
        )

    return patient


def _get_integration(
    clinic_id: int,
    integration_id: Optional[int] = None,
) -> HIEIntegration:
    if integration_id is not None:
        integration = db.session.get(
            HIEIntegration,
            integration_id,
        )

        if not integration:
            raise NotFoundError(
                f"HIE integration {integration_id} not found"
            )

        if integration.clinic_id != clinic_id:
            raise ValidationError(
                "HIE integration does not belong to the supplied clinic"
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

    if not integration:
        raise ValidationError(
            "No active Malaffi integration is configured for this clinic"
        )

    return integration


def _validate_integration(
    integration: HIEIntegration,
) -> None:
    if integration.status != HIEIntegrationStatus.ACTIVE:
        raise ValidationError(
            f"HIE integration is not active: "
            f"{integration.status.value}"
        )

    if integration.provider.lower() != "malaffi":
        raise ValidationError(
            f"Unsupported HIE provider: {integration.provider}"
        )


def _get_provider(
    integration: HIEIntegration,
) -> HIEProvider:
    """
    Build the external HIE provider adapter.

    The provider is deliberately created here rather than inside routes.
    This keeps route handlers independent of the external integration.
    """

    if integration.provider.lower() == "malaffi":
        return MalaffiProvider(
            endpoint=integration.endpoint_url,
        )

    raise ValidationError(
        f"Unsupported HIE provider: {integration.provider}"
    )


def _create_submission(
    *,
    integration: HIEIntegration,
    clinic_id: int,
    patient_id: Optional[int],
    operation: HIEOperation,
    request_data: Optional[dict[str, Any]],
) -> HIESubmission:
    submission = HIESubmission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=operation,
        request_data=request_data,
        success=False,
        retry_count=0,
    )

    db.session.add(submission)
    db.session.flush()

    return submission


def _mark_submission_success(
    submission: HIESubmission,
    response: dict[str, Any],
) -> None:
    submission.success = True
    submission.response_data = response
    submission.status_code = response.get("status_code")
    submission.external_reference = response.get(
        "external_reference"
    )
    submission.error_message = None
    submission.submitted_at = _utcnow()


def _mark_submission_failure(
    submission: HIESubmission,
    error: Exception,
) -> None:
    submission.success = False
    submission.error_message = str(error)
    submission.submitted_at = _utcnow()


def _update_last_sync(
    integration: HIEIntegration,
) -> None:
    integration.last_sync_at = _utcnow()


@transactional
def submit_patient(
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit patient demographic information to the configured HIE provider.
    """

    clinic = _get_clinic(clinic_id)
    patient = _get_patient(clinic.id, patient_id)

    integration = _get_integration(
        clinic_id=clinic.id,
        integration_id=integration_id,
    )

    _validate_integration(integration)

    submission = _create_submission(
        integration=integration,
        clinic_id=clinic.id,
        patient_id=patient.id if patient else None,
        operation=HIEOperation.PATIENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

    try:
        response = provider.submit_patient(payload)

        if not isinstance(response, dict):
            raise ValidationError(
                "HIE provider must return a JSON object"
            )

        _mark_submission_success(
            submission,
            response,
        )

        _update_last_sync(integration)

        return response

    except Exception as exc:
        _mark_submission_failure(
            submission,
            exc,
        )
        raise


@transactional
def submit_clinical_data(
    clinic_id: int,
    patient_id: Optional[int],
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit clinical information for a patient to the configured HIE provider.
    """

    clinic = _get_clinic(clinic_id)
    patient = _get_patient(clinic.id, patient_id)

    integration = _get_integration(
        clinic_id=clinic.id,
        integration_id=integration_id,
    )

    _validate_integration(integration)

    submission = _create_submission(
        integration=integration,
        clinic_id=clinic.id,
        patient_id=patient.id if patient else None,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

    try:
        response = provider.submit_clinical_data(payload)

        if not isinstance(response, dict):
            raise ValidationError(
                "HIE provider must return a JSON object"
            )

        _mark_submission_success(
            submission,
            response,
        )

        _update_last_sync(integration)

        return response

    except Exception as exc:
        _mark_submission_failure(
            submission,
            exc,
        )
        raise


@transactional
def submit_clinical_document(
    clinic_id: int,
    patient_id: Optional[int],
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Submit a clinical document for a patient to the configured HIE provider.
    """

    clinic = _get_clinic(clinic_id)
    patient = _get_patient(clinic.id, patient_id)

    integration = _get_integration(
        clinic_id=clinic.id,
        integration_id=integration_id,
    )

    _validate_integration(integration)

    submission = _create_submission(
        integration=integration,
        clinic_id=clinic.id,
        patient_id=patient.id if patient else None,
        operation=HIEOperation.CLINICAL_DOCUMENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

    try:
        response = provider.submit_clinical_document(payload)

        if not isinstance(response, dict):
            raise ValidationError(
                "HIE provider must return a JSON object"
            )

        _mark_submission_success(
            submission,
            response,
        )

        _update_last_sync(integration)

        return response

    except Exception as exc:
        _mark_submission_failure(
            submission,
            exc,
        )
        raise


@transactional
def query_patient(
    clinic_id: int,
    patient_identifier: str,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Query the external HIE provider for a patient.
    """

    clinic = _get_clinic(clinic_id)

    integration = _get_integration(
        clinic_id=clinic.id,
        integration_id=integration_id,
    )

    _validate_integration(integration)

    if not patient_identifier or not patient_identifier.strip():
        raise ValidationError(
            "Patient identifier is required"
        )

    cleaned_identifier = patient_identifier.strip()

    submission = _create_submission(
        integration=integration,
        clinic_id=clinic.id,
        patient_id=None,
        operation=HIEOperation.PATIENT_QUERY,
        request_data={
            "patient_identifier": cleaned_identifier,
        },
    )

    provider = _get_provider(integration)

    try:
        response = provider.query_patient(
            cleaned_identifier,
        )

        if not isinstance(response, dict):
            raise ValidationError(
                "HIE provider must return a JSON object"
            )

        _mark_submission_success(
            submission,
            response,
        )

        _update_last_sync(integration)

        return response

    except Exception as exc:
        _mark_submission_failure(
            submission,
            exc,
        )
        raise


@transactional
def query_clinical_data(
    clinic_id: int,
    patient_identifier: str,
    filters: Optional[dict[str, Any]] = None,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Query clinical information for a patient from the external HIE provider.
    """

    clinic = _get_clinic(clinic_id)

    integration = _get_integration(
        clinic_id=clinic.id,
        integration_id=integration_id,
    )

    _validate_integration(integration)

    if not patient_identifier or not patient_identifier.strip():
        raise ValidationError(
            "Patient identifier is required"
        )

    cleaned_identifier = patient_identifier.strip()

    submission = _create_submission(
        integration=integration,
        clinic_id=clinic.id,
        patient_id=None,
        operation=HIEOperation.CLINICAL_DATA_QUERY,
        request_data={
            "patient_identifier": cleaned_identifier,
            "filters": filters,
        },
    )

    provider = _get_provider(integration)

    try:
        response = provider.query_clinical_data(
            patient_identifier=cleaned_identifier,
            filters=filters,
        )

        if not isinstance(response, dict):
            raise ValidationError(
                "HIE provider must return a JSON object"
            )

        _mark_submission_success(
            submission,
            response,
        )

        _update_last_sync(integration)

        return response

    except Exception as exc:
        _mark_submission_failure(
            submission,
            exc,
        )
        raise


def get_hie_integration(
    clinic_id: int,
    integration_id: int,
) -> HIEIntegration:
    """
    Retrieve a specific HIE integration belonging to a clinic.
    """

    _get_clinic(clinic_id)

    integration = db.session.get(
        HIEIntegration,
        integration_id,
    )

    if not integration:
        raise NotFoundError(
            f"HIE integration {integration_id} not found"
        )

    if integration.clinic_id != clinic_id:
        raise ValidationError(
            "HIE integration does not belong to the supplied clinic"
        )

    return integration


@transactional
def create_hie_integration(
    clinic_id: int,
    provider: str = "malaffi",
    endpoint_url: Optional[str] = None,
    organization_id: Optional[str] = None,
    facility_id: Optional[str] = None,
) -> HIEIntegration:
    """
    Create an HIE integration for a clinic.

    New integrations start as PENDING and must be activated after the
    external HIE connection has been configured and verified.
    """

    clinic = _get_clinic(clinic_id)

    cleaned_provider = provider.strip().lower()

    if not cleaned_provider:
        raise ValidationError(
            "HIE provider is required"
        )

    if cleaned_provider != "malaffi":
        raise ValidationError(
            f"Unsupported HIE provider: {cleaned_provider}"
        )

    existing = (
        HIEIntegration.query
        .filter_by(
            clinic_id=clinic.id,
            provider=cleaned_provider,
        )
        .first()
    )

    if existing:
        raise ValidationError(
            f"{cleaned_provider} integration already exists "
            f"for clinic {clinic.id}"
        )

    integration = HIEIntegration(
        clinic_id=clinic.id,
        provider=cleaned_provider,
        status=HIEIntegrationStatus.PENDING,
        endpoint_url=endpoint_url,
        organization_id=organization_id,
        facility_id=facility_id,
    )

    db.session.add(integration)

    return integration


@transactional
def update_hie_integration(
    clinic_id: int,
    integration_id: int,
    *,
    provider: Optional[str] = None,
    status: Optional[HIEIntegrationStatus] = None,
    endpoint_url: Optional[str] = None,
    organization_id: Optional[str] = None,
    facility_id: Optional[str] = None,
) -> HIEIntegration:
    """
    Update an existing HIE integration.
    """

    integration = get_hie_integration(
        clinic_id=clinic_id,
        integration_id=integration_id,
    )

    if provider is not None:
        cleaned_provider = provider.strip().lower()

        if not cleaned_provider:
            raise ValidationError(
                "HIE provider cannot be empty"
            )

        if cleaned_provider != "malaffi":
            raise ValidationError(
                f"Unsupported HIE provider: {cleaned_provider}"
            )

        integration.provider = cleaned_provider

    if status is not None:
        integration.status = status

    if endpoint_url is not None:
        integration.endpoint_url = endpoint_url

    if organization_id is not None:
        integration.organization_id = organization_id

    if facility_id is not None:
        integration.facility_id = facility_id

    return integration


def list_hie_submissions(
    *,
    clinic_id: int,
    integration_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    operation: Optional[HIEOperation] = None,
    success: Optional[bool] = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    Return paginated HIE submission history for a clinic.
    """

    _get_clinic(clinic_id)

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

    if success is not None:
        query = query.filter(
            HIESubmission.success == success
        )

    return query.order_by(
        HIESubmission.created_at.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )