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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_clinic(clinic_id: int) -> Clinic:
    clinic = db.session.get(Clinic, clinic_id)

    if not clinic:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _get_patient(
    clinic_id: int,
    patient_id: Optional[int],
) -> Optional[Patient]:
    if patient_id is None:
        return None

    patient = db.session.get(Patient, patient_id)

    if not patient:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

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
            f"Unsupported HIE provider: "
            f"{integration.provider}"
        )


def _get_provider(
    integration: HIEIntegration,
) -> HIEProvider:

    provider_name = integration.provider.lower()

    if provider_name == "malaffi":
        return MalaffiProvider(
            endpoint=integration.endpoint_url,
        )

    raise ValidationError(
        f"Unsupported HIE provider: "
        f"{integration.provider}"
    )


@transactional
def _create_submission(
    *,
    integration_id: int,
    clinic_id: int,
    patient_id: Optional[int],
    operation: HIEOperation,
    request_data: Optional[dict[str, Any]],
) -> int:

    submission = HIESubmission(
        integration_id=integration_id,
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

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    if not submission:
        raise NotFoundError(
            f"HIE submission {submission_id} not found"
        )

    submission.status = HIESubmissionStatus.SUCCESS
    submission.response_data = response
    submission.status_code = response.get("status_code")
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

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    if not submission:
        raise NotFoundError(
            f"HIE submission {submission_id} not found"
        )

    submission.status = HIESubmissionStatus.FAILED
    submission.error_message = str(error)
    submission.submitted_at = _utcnow()


@transactional
def _update_last_sync(
    integration_id: int,
) -> None:

    integration = db.session.get(
        HIEIntegration,
        integration_id,
    )

    if not integration:
        raise NotFoundError(
            f"HIE integration {integration_id} not found"
        )

    integration.last_sync_at = _utcnow()


def submit_patient(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:

    _get_clinic(clinic_id)
    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(integration)

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.PATIENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

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
        integration.id,
    )

    return response


def submit_clinical_data(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:

    _get_clinic(clinic_id)
    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(integration)

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

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
        integration.id,
    )

    return response


def submit_clinical_document(
    *,
    clinic_id: int,
    patient_id: int,
    payload: dict[str, Any],
    integration_id: Optional[int] = None,
) -> dict[str, Any]:

    _get_clinic(clinic_id)
    _get_patient(
        clinic_id,
        patient_id,
    )

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(integration)

    submission_id = _create_submission(
        integration_id=integration.id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=HIEOperation.CLINICAL_DOCUMENT_SUBMISSION,
        request_data=payload,
    )

    provider = _get_provider(integration)

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
        integration.id,
    )

    return response


def query_patient(
    *,
    clinic_id: int,
    patient_identifier: str,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:

    _get_clinic(clinic_id)

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(integration)

    provider = _get_provider(integration)

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
        integration.id,
    )

    return response


def query_clinical_data(
    *,
    clinic_id: int,
    patient_identifier: str,
    filters: Optional[dict[str, Any]] = None,
    integration_id: Optional[int] = None,
) -> dict[str, Any]:

    _get_clinic(clinic_id)

    integration = _get_integration(
        clinic_id,
        integration_id,
    )

    _validate_integration(integration)

    provider = _get_provider(integration)

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
        integration.id,
    )

    return response


def get_hie_integration(
    clinic_id: int,
    integration_id: int,
) -> HIEIntegration:

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

    _get_clinic(clinic_id)

    provider = provider.strip().lower()

    if not provider:
        raise ValidationError(
            "Provider is required"
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

        integration.provider = provider

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
    status: Optional[HIESubmissionStatus] = None,
    page: int = 1,
    per_page: int = 20,
):
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

    if status is not None:
        query = query.filter(
            HIESubmission.status == status
        )

    pagination = (
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

    return pagination