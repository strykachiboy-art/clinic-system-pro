from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.hie.services import hie_service


# ============================================================================
# Helpers
# ============================================================================


def make_clinic(*, clinic_id=1):
    return SimpleNamespace(
        id=clinic_id,
        name=f"Clinic {clinic_id}",
    )


def make_patient(*, patient_id=1, clinic_id=1):
    return SimpleNamespace(
        id=patient_id,
        clinic_id=clinic_id,
    )


def make_integration(
    *,
    integration_id=1,
    clinic_id=1,
    provider="malaffi",
    status=HIEIntegrationStatus.ACTIVE,
    endpoint_url="https://hie.example.com",
    organization_id="ORG-001",
    facility_id="FAC-001",
    last_sync_at=None,
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=integration_id,
        clinic_id=clinic_id,
        provider=provider,
        status=status,
        endpoint_url=endpoint_url,
        organization_id=organization_id,
        facility_id=facility_id,
        last_sync_at=last_sync_at,
        created_at=now,
        updated_at=now,
    )


def make_submission(
    *,
    submission_id=1,
    integration_id=1,
    clinic_id=1,
    patient_id=1,
    operation=HIEOperation.PATIENT_SUBMISSION,
    status=HIESubmissionStatus.PENDING,
    request_data=None,
    response_data=None,
    status_code=None,
    external_reference=None,
    error_message=None,
    retry_count=0,
    submitted_at=None,
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=submission_id,
        integration_id=integration_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        operation=operation,
        status=status,
        request_data=request_data,
        response_data=response_data,
        status_code=status_code,
        external_reference=external_reference,
        error_message=error_message,
        retry_count=retry_count,
        submitted_at=submitted_at,
        created_at=now,
        updated_at=now,
    )


class FakeSubmission:
    _next_id = 1

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = FakeSubmission._next_id
        FakeSubmission._next_id += 1


class FakeIntegration:
    _next_id = 1

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = FakeIntegration._next_id
        FakeIntegration._next_id += 1


@pytest.fixture
def no_transaction(monkeypatch):
    """
    Prevent transactional wrappers from performing real commit/rollback
    work while exercising service behavior.
    """
    monkeypatch.setattr(
        hie_service.db.session,
        "commit",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service.db.session,
        "rollback",
        Mock(),
    )


# ============================================================================
# _GET_CLINIC
# ============================================================================


def test_get_clinic_rejects_none():
    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        hie_service._get_clinic(None)


def test_get_clinic_rejects_non_positive_id():
    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        hie_service._get_clinic(0)

    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        hie_service._get_clinic(-1)


def test_get_clinic_returns_clinic(monkeypatch):
    clinic = make_clinic(clinic_id=4)

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=clinic),
    )

    result = hie_service._get_clinic(4)

    assert result is clinic
    hie_service.db.session.get.assert_called_once_with(
        hie_service.Clinic,
        4,
    )


def test_get_clinic_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="Clinic 99 not found",
    ):
        hie_service._get_clinic(99)


# ============================================================================
# _GET_PATIENT
# ============================================================================


def test_get_patient_none_returns_none():
    assert hie_service._get_patient(1, None) is None


def test_get_patient_rejects_invalid_id():
    with pytest.raises(ValidationError, match="Invalid patient ID"):
        hie_service._get_patient(1, 0)


def test_get_patient_returns_patient(monkeypatch):
    patient = make_patient(
        patient_id=5,
        clinic_id=2,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    result = hie_service._get_patient(
        2,
        5,
    )

    assert result is patient


def test_get_patient_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="Patient 10 not found",
    ):
        hie_service._get_patient(1, 10)


def test_get_patient_rejects_wrong_clinic(monkeypatch):
    patient = make_patient(
        patient_id=5,
        clinic_id=2,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    with pytest.raises(
        ValidationError,
        match="Patient does not belong to the clinic",
    ):
        hie_service._get_patient(99, 5)


# ============================================================================
# _GET_INTEGRATION
# ============================================================================


def test_get_integration_rejects_invalid_clinic():
    with pytest.raises(ValidationError, match="Invalid clinic ID"):
        hie_service._get_integration(0)


def test_get_integration_rejects_invalid_integration_id():
    with pytest.raises(
        ValidationError,
        match="Invalid HIE integration ID",
    ):
        hie_service._get_integration(1, 0)


def test_get_integration_by_id(monkeypatch):
    integration = make_integration(
        integration_id=8,
        clinic_id=3,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    result = hie_service._get_integration(
        3,
        8,
    )

    assert result is integration


def test_get_integration_by_id_not_found(monkeypatch):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="HIE integration 8 not found",
    ):
        hie_service._get_integration(3, 8)


def test_get_integration_by_id_rejects_other_clinic(monkeypatch):
    integration = make_integration(
        integration_id=8,
        clinic_id=3,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration does not belong to the clinic",
    ):
        hie_service._get_integration(99, 8)


def test_get_active_malaffi_integration(monkeypatch):
    integration = make_integration(
        integration_id=12,
        clinic_id=4,
        provider="malaffi",
        status=HIEIntegrationStatus.ACTIVE,
    )

    scalars = Mock()
    scalars.first.return_value = integration

    execute_result = Mock()
    execute_result.scalars.return_value = scalars

    monkeypatch.setattr(
        hie_service.db.session,
        "execute",
        Mock(return_value=execute_result),
    )

    result = hie_service._get_integration(
        clinic_id=4,
    )

    assert result is integration
    execute_result.scalars.assert_called_once_with()
    scalars.first.assert_called_once_with()


def test_get_integration_requires_active_malaffi(monkeypatch):
    scalars = Mock()
    scalars.first.return_value = None

    execute_result = Mock()
    execute_result.scalars.return_value = scalars

    monkeypatch.setattr(
        hie_service.db.session,
        "execute",
        Mock(return_value=execute_result),
    )

    with pytest.raises(
        ValidationError,
        match="No active Malaffi integration is configured for this clinic",
    ):
        hie_service._get_integration(
            clinic_id=4,
        )


# ============================================================================
# _VALIDATE_INTEGRATION
# ============================================================================


def test_validate_integration_requires_integration():
    with pytest.raises(
        ValidationError,
        match="HIE integration is required",
    ):
        hie_service._validate_integration(None)


def test_validate_integration_requires_active_status():
    integration = make_integration(
        status=HIEIntegrationStatus.PENDING,
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration is not active",
    ):
        hie_service._validate_integration(integration)


def test_validate_integration_requires_provider():
    integration = make_integration(
        provider="   ",
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration provider is not configured",
    ):
        hie_service._validate_integration(integration)


def test_validate_integration_rejects_unsupported_provider():
    integration = make_integration(
        provider="epic",
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider",
    ):
        hie_service._validate_integration(integration)


def test_validate_integration_accepts_malaffi():
    integration = make_integration(
        provider="MALAFFI",
    )

    hie_service._validate_integration(integration)


# ============================================================================
# _GET_PROVIDER
# ============================================================================


def test_get_provider_returns_malaffi(monkeypatch):
    provider = object()

    malaffi = Mock(return_value=provider)

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        malaffi,
    )

    integration = make_integration(
        endpoint_url="https://malaffi.example.com",
    )

    result = hie_service._get_provider(integration)

    assert result is provider

    malaffi.assert_called_once_with(
        endpoint=integration.endpoint_url,
    )


def test_get_provider_rejects_unsupported_provider():
    integration = make_integration(
        provider="unsupported",
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider",
    ):
        hie_service._get_provider(integration)


# ============================================================================
# _VALIDATE_PATIENT_IDENTIFIER
# ============================================================================


def test_validate_patient_identifier_requires_value():
    with pytest.raises(
        ValidationError,
        match="Patient identifier is required",
    ):
        hie_service._validate_patient_identifier(None)


def test_validate_patient_identifier_rejects_blank():
    with pytest.raises(
        ValidationError,
        match="Patient identifier is required",
    ):
        hie_service._validate_patient_identifier("   ")


def test_validate_patient_identifier_strips_whitespace():
    assert (
        hie_service._validate_patient_identifier(
            "  MRN-123  "
        )
        == "MRN-123"
    )


# ============================================================================
# _VALIDATE_SUBMISSION_CONTEXT
# ============================================================================


def test_validate_submission_context_requires_integration():
    with pytest.raises(
        ValidationError,
        match="HIE integration is required",
    ):
        hie_service._validate_submission_context(
            integration=None,
            clinic_id=1,
            patient_id=None,
        )


def test_validate_submission_context_rejects_wrong_integration_clinic():
    integration = make_integration(
        clinic_id=2,
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration does not belong to the clinic",
    ):
        hie_service._validate_submission_context(
            integration=integration,
            clinic_id=1,
            patient_id=None,
        )


def test_validate_submission_context_accepts_no_patient():
    integration = make_integration(
        clinic_id=1,
    )

    hie_service._validate_submission_context(
        integration=integration,
        clinic_id=1,
        patient_id=None,
    )


def test_validate_submission_context_rejects_wrong_patient_clinic(
    monkeypatch,
):
    integration = make_integration(
        clinic_id=1,
    )

    patient = make_patient(
        patient_id=7,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=patient),
    )

    with pytest.raises(
        ValidationError,
        match="Patient does not belong to the clinic",
    ):
        hie_service._validate_submission_context(
            integration=integration,
            clinic_id=1,
            patient_id=7,
        )


# ============================================================================
# _CREATE_SUBMISSION
# ============================================================================


def test_create_submission_success(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=11,
        clinic_id=3,
    )

    added = []

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    monkeypatch.setattr(
        hie_service,
        "HIESubmission",
        FakeSubmission,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "add",
        lambda obj: added.append(obj),
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "flush",
        Mock(),
    )

    submission_id = hie_service._create_submission(
        integration_id=11,
        clinic_id=3,
        patient_id=None,
        operation=HIEOperation.PATIENT_QUERY,
        request_data={
            "patient_identifier": "MRN-100",
        },
    )

    assert submission_id == added[0].id
    assert added[0].integration_id == 11
    assert added[0].clinic_id == 3
    assert added[0].patient_id is None
    assert added[0].operation == HIEOperation.PATIENT_QUERY
    assert added[0].status == HIESubmissionStatus.PENDING
    assert added[0].request_data == {
        "patient_identifier": "MRN-100",
    }
    assert added[0].retry_count == 0


def test_create_submission_rejects_invalid_clinic(
    no_transaction,
):
    with pytest.raises(
        ValidationError,
        match="Invalid clinic ID",
    ):
        hie_service._create_submission(
            integration_id=1,
            clinic_id=0,
            patient_id=None,
            operation=HIEOperation.PATIENT_QUERY,
            request_data={},
        )


def test_create_submission_rejects_invalid_integration(
    no_transaction,
):
    with pytest.raises(
        ValidationError,
        match="Invalid HIE integration ID",
    ):
        hie_service._create_submission(
            integration_id=0,
            clinic_id=1,
            patient_id=None,
            operation=HIEOperation.PATIENT_QUERY,
            request_data={},
        )


def test_create_submission_rejects_missing_integration(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="HIE integration 99 not found",
    ):
        hie_service._create_submission(
            integration_id=99,
            clinic_id=1,
            patient_id=None,
            operation=HIEOperation.PATIENT_QUERY,
            request_data={},
        )


def test_create_submission_rejects_invalid_operation(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=1,
        clinic_id=1,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid HIE operation",
    ):
        hie_service._create_submission(
            integration_id=1,
            clinic_id=1,
            patient_id=None,
            operation="patient_query",
            request_data={},
        )


def test_create_submission_rejects_non_dict_request_data(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=1,
        clinic_id=1,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="HIE request data must be an object",
    ):
        hie_service._create_submission(
            integration_id=1,
            clinic_id=1,
            patient_id=None,
            operation=HIEOperation.PATIENT_QUERY,
            request_data="invalid",
        )


# ============================================================================
# SUBMISSION STATUS HELPERS
# ============================================================================


def test_mark_submission_success(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=20,
        retry_count=2,
        error_message="old error",
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=submission),
    )

    response = {
        "status_code": 200,
        "external_reference": "EXT-123",
        "patient": {
            "id": "ABC",
        },
    }

    before = datetime.now(timezone.utc)

    hie_service._mark_submission_success(
        20,
        response,
    )

    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.response_data == response
    assert submission.status_code == 200
    assert submission.external_reference == "EXT-123"
    assert submission.error_message is None
    assert submission.submitted_at is not None
    assert submission.submitted_at >= before


def test_mark_submission_success_rejects_invalid_id(
    no_transaction,
):
    with pytest.raises(
        ValidationError,
        match="Invalid HIE submission ID",
    ):
        hie_service._mark_submission_success(
            0,
            {},
        )


def test_mark_submission_success_requires_submission(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="HIE submission 99 not found",
    ):
        hie_service._mark_submission_success(
            99,
            {},
        )


def test_mark_submission_success_requires_dict(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=9,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=submission),
    )

    with pytest.raises(
        ValidationError,
        match="HIE provider response must be an object",
    ):
        hie_service._mark_submission_success(
            9,
            [],
        )


def test_mark_submission_failure_increments_retry_count(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=20,
        retry_count=2,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=submission),
    )

    error = RuntimeError("Provider unavailable")

    hie_service._mark_submission_failure(
        20,
        error,
    )

    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Provider unavailable"
    assert submission.retry_count == 3
    assert submission.submitted_at is not None


def test_mark_submission_failure_handles_none_retry_count(
    monkeypatch,
    no_transaction,
):
    submission = make_submission(
        submission_id=20,
        retry_count=0,
    )
    submission.retry_count = None

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=submission),
    )

    hie_service._mark_submission_failure(
        20,
        RuntimeError("Failure"),
    )

    assert submission.retry_count == 1


# ============================================================================
# LAST SYNC
# ============================================================================


def test_update_last_sync(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=4,
        last_sync_at=None,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=integration),
    )

    before = datetime.now(timezone.utc)

    hie_service._update_last_sync(4)

    assert integration.last_sync_at is not None
    assert integration.last_sync_at >= before


def test_update_last_sync_rejects_invalid_id(
    no_transaction,
):
    with pytest.raises(
        ValidationError,
        match="Invalid HIE integration ID",
    ):
        hie_service._update_last_sync(0)


def test_update_last_sync_requires_integration(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        NotFoundError,
        match="HIE integration 99 not found",
    ):
        hie_service._update_last_sync(99)


# ============================================================================
# SUBMIT PATIENT
# ============================================================================


def test_submit_patient_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=5,
        clinic_id=1,
    )

    provider_response = {
        "status_code": 201,
        "external_reference": "PAT-001",
    }

    provider = Mock()
    provider.submit_patient.return_value = provider_response

    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_patient",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=100),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_success",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_update_last_sync",
        Mock(),
    )

    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
    }

    result = hie_service.submit_patient(
        clinic_id=1,
        patient_id=7,
        payload=payload,
        integration_id=5,
    )

    assert result == provider_response

    hie_service._get_clinic.assert_called_once_with(1)
    hie_service._get_patient.assert_called_once_with(1, 7)
    hie_service._create_submission.assert_called_once_with(
        integration_id=5,
        clinic_id=1,
        patient_id=7,
        operation=HIEOperation.PATIENT_SUBMISSION,
        request_data=payload,
    )
    provider.submit_patient.assert_called_once_with(payload)
    hie_service._mark_submission_success.assert_called_once_with(
        100,
        provider_response,
    )
    hie_service._update_last_sync.assert_called_once_with(5)


def test_submit_patient_marks_failure_and_reraises(
    monkeypatch,
):
    integration = make_integration(
        integration_id=5,
        clinic_id=1,
    )

    provider = Mock()
    provider.submit_patient.side_effect = RuntimeError(
        "Provider failure"
    )

    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_patient",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=100),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_failure",
        Mock(),
    )

    with pytest.raises(
        RuntimeError,
        match="Provider failure",
    ):
        hie_service.submit_patient(
            clinic_id=1,
            patient_id=7,
            payload={},
            integration_id=5,
        )

    hie_service._mark_submission_failure.assert_called_once()
    hie_service._update_last_sync = Mock()

    assert not hie_service._update_last_sync.called


# ============================================================================
# SUBMIT CLINICAL DATA
# ============================================================================


def test_submit_clinical_data_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=6,
        clinic_id=2,
    )

    provider = Mock()
    provider.submit_clinical_data.return_value = {
        "status_code": 200,
        "external_reference": "CLIN-1",
    }

    monkeypatch.setattr(hie_service, "_get_clinic", Mock())
    monkeypatch.setattr(hie_service, "_get_patient", Mock())
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=200),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_success",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_update_last_sync",
        Mock(),
    )

    payload = {
        "diagnosis": "Malaria",
    }

    result = hie_service.submit_clinical_data(
        clinic_id=2,
        patient_id=10,
        payload=payload,
        integration_id=6,
    )

    assert result["status_code"] == 200
    provider.submit_clinical_data.assert_called_once_with(
        payload
    )

    hie_service._create_submission.assert_called_once_with(
        integration_id=6,
        clinic_id=2,
        patient_id=10,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
        request_data=payload,
    )


# ============================================================================
# SUBMIT CLINICAL DOCUMENT
# ============================================================================


def test_submit_clinical_document_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=7,
        clinic_id=3,
    )

    provider = Mock()
    provider.submit_clinical_document.return_value = {
        "status_code": 201,
        "external_reference": "DOC-1",
    }

    monkeypatch.setattr(hie_service, "_get_clinic", Mock())
    monkeypatch.setattr(hie_service, "_get_patient", Mock())
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=300),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_success",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_update_last_sync",
        Mock(),
    )

    payload = {
        "document_type": "consultation",
        "content": "Clinical note",
    }

    result = hie_service.submit_clinical_document(
        clinic_id=3,
        patient_id=11,
        payload=payload,
        integration_id=7,
    )

    assert result["external_reference"] == "DOC-1"

    provider.submit_clinical_document.assert_called_once_with(
        payload
    )


# ============================================================================
# QUERY PATIENT
# ============================================================================


def test_query_patient_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=8,
        clinic_id=4,
    )

    provider = Mock()
    provider.query_patient.return_value = {
        "status_code": 200,
        "patient": {
            "identifier": "MRN-1",
        },
    }

    monkeypatch.setattr(hie_service, "_get_clinic", Mock())
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=400),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_success",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_update_last_sync",
        Mock(),
    )

    result = hie_service.query_patient(
        clinic_id=4,
        patient_identifier="  MRN-1  ",
        integration_id=8,
    )

    assert result["status_code"] == 200

    provider.query_patient.assert_called_once_with(
        "MRN-1"
    )

    hie_service._create_submission.assert_called_once_with(
        integration_id=8,
        clinic_id=4,
        patient_id=None,
        operation=HIEOperation.PATIENT_QUERY,
        request_data={
            "patient_identifier": "MRN-1",
        },
    )


def test_query_patient_requires_identifier(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Patient identifier is required",
    ):
        hie_service.query_patient(
            clinic_id=1,
            patient_identifier="   ",
        )


# ============================================================================
# QUERY CLINICAL DATA
# ============================================================================


def test_query_clinical_data_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=9,
        clinic_id=5,
    )

    provider = Mock()
    provider.query_clinical_data.return_value = {
        "status_code": 200,
        "records": [],
    }

    monkeypatch.setattr(hie_service, "_get_clinic", Mock())
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )
    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(return_value=provider),
    )
    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(return_value=500),
    )
    monkeypatch.setattr(
        hie_service,
        "_mark_submission_success",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_update_last_sync",
        Mock(),
    )

    filters = {
        "from": "2026-01-01",
        "to": "2026-01-31",
    }

    result = hie_service.query_clinical_data(
        clinic_id=5,
        patient_identifier="MRN-20",
        filters=filters,
        integration_id=9,
    )

    assert result["status_code"] == 200

    provider.query_clinical_data.assert_called_once_with(
        "MRN-20",
        filters,
    )

    hie_service._create_submission.assert_called_once_with(
        integration_id=9,
        clinic_id=5,
        patient_id=None,
        operation=HIEOperation.CLINICAL_DATA_QUERY,
        request_data={
            "patient_identifier": "MRN-20",
            "filters": filters,
        },
    )


def test_query_clinical_data_rejects_non_dict_filters(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Clinical data filters must be an object",
    ):
        hie_service.query_clinical_data(
            clinic_id=1,
            patient_identifier="MRN-1",
            filters=[],
        )


# ============================================================================
# INTEGRATION MANAGEMENT
# ============================================================================


def test_get_hie_integration_success(
    monkeypatch,
):
    integration = make_integration(
        integration_id=15,
        clinic_id=6,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    result = hie_service.get_hie_integration(
        clinic_id=6,
        integration_id=15,
    )

    assert result is integration

    hie_service._get_clinic.assert_called_once_with(6)
    hie_service._get_integration.assert_called_once_with(
        6,
        15,
    )


def test_create_hie_integration_success(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    monkeypatch.setattr(
        hie_service,
        "HIEIntegration",
        FakeIntegration,
    )

    added = []

    monkeypatch.setattr(
        hie_service.db.session,
        "add",
        lambda obj: added.append(obj),
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "flush",
        Mock(),
    )

    result = hie_service.create_hie_integration(
        clinic_id=8,
        provider=" MALAFFI ",
        endpoint_url="  https://hie.example.com  ",
        organization_id=" ORG-8 ",
        facility_id=" FAC-8 ",
    )

    assert result is added[0]
    assert result.clinic_id == 8
    assert result.provider == "malaffi"
    assert result.status == HIEIntegrationStatus.PENDING
    assert result.endpoint_url == "https://hie.example.com"
    assert result.organization_id == "ORG-8"
    assert result.facility_id == "FAC-8"


def test_create_hie_integration_defaults_provider(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    monkeypatch.setattr(
        hie_service,
        "HIEIntegration",
        FakeIntegration,
    )

    monkeypatch.setattr(
        hie_service.db.session,
        "add",
        Mock(),
    )
    monkeypatch.setattr(
        hie_service.db.session,
        "flush",
        Mock(),
    )

    result = hie_service.create_hie_integration(
        clinic_id=1,
    )

    assert result.provider == "malaffi"
    assert result.status == HIEIntegrationStatus.PENDING


def test_create_hie_integration_rejects_missing_provider(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Provider is required",
    ):
        hie_service.create_hie_integration(
            clinic_id=1,
            provider=None,
        )


def test_create_hie_integration_rejects_unsupported_provider(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider: epic",
    ):
        hie_service.create_hie_integration(
            clinic_id=1,
            provider="epic",
        )


def test_create_hie_integration_rejects_blank_organization_id(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Organization ID cannot be empty",
    ):
        hie_service.create_hie_integration(
            clinic_id=1,
            organization_id="   ",
        )


def test_create_hie_integration_rejects_blank_facility_id(
    monkeypatch,
    no_transaction,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Facility ID cannot be empty",
    ):
        hie_service.create_hie_integration(
            clinic_id=1,
            facility_id="   ",
        )


def test_update_hie_integration_success(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    result = hie_service.update_hie_integration(
        clinic_id=9,
        integration_id=20,
        provider=" MALAFFI ",
        status=HIEIntegrationStatus.ACTIVE,
        endpoint_url=" https://new.example.com ",
        organization_id=" ORG-NEW ",
        facility_id=" FAC-NEW ",
    )

    assert result is integration
    assert result.provider == "malaffi"
    assert result.status == HIEIntegrationStatus.ACTIVE
    assert result.endpoint_url == "https://new.example.com"
    assert result.organization_id == "ORG-NEW"
    assert result.facility_id == "FAC-NEW"


def test_update_hie_integration_rejects_blank_provider(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Provider cannot be empty",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            provider="   ",
        )


def test_update_hie_integration_rejects_unsupported_provider(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider: epic",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            provider="epic",
        )


def test_update_hie_integration_rejects_invalid_status(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid HIE integration status",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            status="active",
        )


def test_update_hie_integration_rejects_blank_endpoint(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Endpoint URL cannot be empty",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            endpoint_url="   ",
        )


def test_update_hie_integration_rejects_blank_organization(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Organization ID cannot be empty",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            organization_id="   ",
        )


def test_update_hie_integration_rejects_blank_facility(
    monkeypatch,
    no_transaction,
):
    integration = make_integration(
        integration_id=20,
        clinic_id=9,
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(return_value=integration),
    )

    with pytest.raises(
        ValidationError,
        match="Facility ID cannot be empty",
    ):
        hie_service.update_hie_integration(
            clinic_id=9,
            integration_id=20,
            facility_id="   ",
        )


# ============================================================================
# LIST HIE SUBMISSIONS
# ============================================================================


def test_list_hie_submissions_rejects_invalid_page(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Page must be greater than or equal to 1",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            page=0,
        )


def test_list_hie_submissions_rejects_invalid_per_page(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="per_page must be between 1 and 100",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            per_page=101,
        )


def test_list_hie_submissions_rejects_invalid_integration_id(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid HIE integration ID",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            integration_id=0,
        )


def test_list_hie_submissions_rejects_invalid_patient_id(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid patient ID",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            patient_id=0,
        )


def test_list_hie_submissions_rejects_invalid_operation(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid HIE operation",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            operation="patient_query",
        )


def test_list_hie_submissions_rejects_invalid_status(
    monkeypatch,
):
    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid HIE submission status",
    ):
        hie_service.list_hie_submissions(
            clinic_id=1,
            status="success",
        )