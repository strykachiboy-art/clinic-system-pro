import pytest

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.hie.models.hie_model import (
    HIEIntegration,
    HIESubmission,
)
from app.modules.hie.services import hie_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_integration(
    db,
    clinic,
    *,
    provider="malaffi",
    status=HIEIntegrationStatus.ACTIVE,
    endpoint_url="https://hie.test",
    organization_id="ORG-001",
    facility_id="FAC-001",
):
    integration = HIEIntegration(
        clinic_id=clinic.id,
        provider=provider,
        status=status,
        endpoint_url=endpoint_url,
        organization_id=organization_id,
        facility_id=facility_id,
    )
    db.session.add(integration)
    db.session.commit()
    return integration


def create_submission(
    db,
    integration,
    clinic,
    *,
    patient_id=None,
    operation=HIEOperation.PATIENT_SUBMISSION,
    status=HIESubmissionStatus.PENDING,
    request_data=None,
    response_data=None,
    external_reference=None,
    status_code=None,
    error_message=None,
    retry_count=0,
):
    submission = HIESubmission(
        integration_id=integration.id,
        clinic_id=clinic.id,
        patient_id=patient_id,
        operation=operation,
        status=status,
        request_data=request_data,
        response_data=response_data,
        external_reference=external_reference,
        status_code=status_code,
        error_message=error_message,
        retry_count=retry_count,
    )
    db.session.add(submission)
    db.session.commit()
    return submission


def fake_provider(monkeypatch):
    class FakeProvider:
        def __init__(self, endpoint=None):
            self.endpoint = endpoint
            self.calls = []

        def submit_patient(self, payload):
            self.calls.append(("submit_patient", payload))
            return {
                "status_code": 201,
                "external_reference": "EXT-PAT-001",
                "patient_id": "PAT-001",
            }

        def submit_clinical_data(self, payload):
            self.calls.append(("submit_clinical_data", payload))
            return {
                "status_code": 201,
                "external_reference": "EXT-CLIN-001",
            }

        def submit_clinical_document(self, payload):
            self.calls.append(("submit_clinical_document", payload))
            return {
                "status_code": 201,
                "external_reference": "EXT-DOC-001",
            }

        def query_patient(self, patient_identifier):
            self.calls.append(("query_patient", patient_identifier))
            return {
                "status_code": 200,
                "external_reference": "QUERY-PAT-001",
                "patient_identifier": patient_identifier,
            }

        def query_clinical_data(
            self,
            patient_identifier,
            filters=None,
        ):
            self.calls.append(
                (
                    "query_clinical_data",
                    patient_identifier,
                    filters,
                )
            )
            return {
                "status_code": 200,
                "patient_identifier": patient_identifier,
                "filters": filters,
                "records": [],
            }

    provider = FakeProvider()
    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: provider,
    )
    return provider


# ---------------------------------------------------------------------------
# Clinic / patient / integration helpers
# ---------------------------------------------------------------------------


def test_get_clinic_returns_existing_clinic(db, clinic):
    result = hie_service._get_clinic(clinic.id)

    assert result.id == clinic.id


def test_get_clinic_raises_for_missing_clinic(app):
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        hie_service._get_clinic(999999)


def test_get_patient_returns_existing_patient(
    patient,
    clinic,
):
    result = hie_service._get_patient(
        clinic.id,
        patient.id,
    )

    assert result.id == patient.id


def test_get_patient_returns_none_when_patient_id_is_none(
    clinic,
):
    result = hie_service._get_patient(
        clinic.id,
        None,
    )

    assert result is None


def test_get_patient_raises_for_missing_patient(
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match=r"Patient 999999 not found",
    ):
        hie_service._get_patient(
            clinic.id,
            999999,
        )


def test_get_patient_rejects_cross_clinic_patient(
    db,
    clinic,
    make_clinic,
    make_patient,
):
    other_clinic = make_clinic(
        name="Other HIE Clinic",
    )

    other_patient = make_patient(
        other_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="Patient does not belong to the supplied clinic",
    ):
        hie_service._get_patient(
            clinic.id,
            other_patient.id,
        )


def test_get_integration_by_id_returns_integration(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    result = hie_service._get_integration(
        clinic.id,
        integration.id,
    )

    assert result.id == integration.id


def test_get_integration_raises_for_missing_integration(
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match=r"HIE integration 999999 not found",
    ):
        hie_service._get_integration(
            clinic.id,
            999999,
        )


def test_get_integration_rejects_cross_clinic_integration(
    db,
    clinic,
    make_clinic,
):
    other_clinic = make_clinic(
        name="Other HIE Clinic",
    )

    integration = create_integration(
        db,
        other_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration does not belong to the supplied clinic",
    ):
        hie_service._get_integration(
            clinic.id,
            integration.id,
        )


def test_get_integration_finds_active_malaffi_integration(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        provider="malaffi",
        status=HIEIntegrationStatus.ACTIVE,
    )

    result = hie_service._get_integration(
        clinic.id,
    )

    assert result.id == integration.id


def test_get_integration_ignores_inactive_malaffi_integration(
    db,
    clinic,
):
    create_integration(
        db,
        clinic,
        status=HIEIntegrationStatus.SUSPENDED,
    )

    with pytest.raises(
        ValidationError,
        match="No active Malaffi integration is configured for this clinic",
    ):
        hie_service._get_integration(
            clinic.id,
        )


def test_get_integration_ignores_non_malaffi_provider(
    db,
    clinic,
):
    create_integration(
        db,
        clinic,
        provider="other-provider",
        status=HIEIntegrationStatus.ACTIVE,
    )

    with pytest.raises(
        ValidationError,
        match="No active Malaffi integration is configured for this clinic",
    ):
        hie_service._get_integration(
            clinic.id,
        )


# ---------------------------------------------------------------------------
# Integration validation / provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        HIEIntegrationStatus.PENDING,
        HIEIntegrationStatus.SUSPENDED,
        HIEIntegrationStatus.DISABLED,
    ],
)
def test_validate_integration_rejects_non_active_status(
    db,
    clinic,
    status,
):
    integration = create_integration(
        db,
        clinic,
        status=status,
    )

    with pytest.raises(
        ValidationError,
        match=rf"HIE integration is not active: {status.value}",
    ):
        hie_service._validate_integration(integration)


@pytest.mark.parametrize(
    "provider",
    [
        "hl7",
        "fhir",
        "other",
    ],
)
def test_validate_integration_rejects_unsupported_provider(
    db,
    clinic,
    provider,
):
    integration = create_integration(
        db,
        clinic,
        provider=provider,
        status=HIEIntegrationStatus.ACTIVE,
    )

    with pytest.raises(
        ValidationError,
        match=rf"Unsupported HIE provider: {provider}",
    ):
        hie_service._validate_integration(integration)


def test_validate_integration_accepts_active_malaffi(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        provider="malaffi",
        status=HIEIntegrationStatus.ACTIVE,
    )

    assert hie_service._validate_integration(integration) is None


def test_validate_integration_accepts_case_insensitive_malaffi(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        provider="MALAFFI",
        status=HIEIntegrationStatus.ACTIVE,
    )

    assert hie_service._validate_integration(integration) is None


def test_get_provider_returns_malaffi_provider(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        endpoint_url="https://malaffi.example",
    )

    provider = hie_service._get_provider(integration)

    assert isinstance(
        provider,
        hie_service.MalaffiProvider,
    )
    assert provider.endpoint == "https://malaffi.example"


def test_get_provider_rejects_unsupported_provider(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        provider="hl7",
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider: hl7",
    ):
        hie_service._get_provider(integration)


# ---------------------------------------------------------------------------
# Submission lifecycle helpers
# ---------------------------------------------------------------------------


def test_create_submission_creates_pending_submission(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    submission_id = hie_service._create_submission(
        integration_id=integration.id,
        clinic_id=clinic.id,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_SUBMISSION,
        request_data={
            "first_name": "Jane",
        },
    )

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    assert submission is not None
    assert submission.integration_id == integration.id
    assert submission.clinic_id == clinic.id
    assert submission.patient_id == patient.id
    assert submission.operation == HIEOperation.PATIENT_SUBMISSION
    assert submission.status == HIESubmissionStatus.PENDING
    assert submission.request_data == {
        "first_name": "Jane",
    }
    assert submission.retry_count == 0


def test_create_submission_supports_query_without_patient(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    submission_id = hie_service._create_submission(
        integration_id=integration.id,
        clinic_id=clinic.id,
        patient_id=None,
        operation=HIEOperation.PATIENT_QUERY,
        request_data={
            "patient_identifier": "MRN-001",
        },
    )

    submission = db.session.get(
        HIESubmission,
        submission_id,
    )

    assert submission.patient_id is None
    assert submission.operation == HIEOperation.PATIENT_QUERY


def test_mark_submission_success_updates_submission(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    submission = create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
    )

    response = {
        "status_code": 201,
        "external_reference": "EXT-001",
        "accepted": True,
    }

    hie_service._mark_submission_success(
        submission.id,
        response,
    )

    db.session.refresh(submission)

    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.response_data == response
    assert submission.status_code == 201
    assert submission.external_reference == "EXT-001"
    assert submission.error_message is None
    assert submission.submitted_at is not None


def test_mark_submission_success_allows_missing_optional_response_fields(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    submission = create_submission(
        db,
        integration,
        clinic,
    )

    response = {
        "status_code": 200,
    }

    hie_service._mark_submission_success(
        submission.id,
        response,
    )

    db.session.refresh(submission)

    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.response_data == response
    assert submission.status_code == 200
    assert submission.external_reference is None
    assert submission.error_message is None
    assert submission.submitted_at is not None


def test_mark_submission_success_raises_for_missing_submission(
    app,
):
    with pytest.raises(
        NotFoundError,
        match=r"HIE submission 999999 not found",
    ):
        hie_service._mark_submission_success(
            999999,
            {"status_code": 200},
        )


def test_mark_submission_failure_updates_submission(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    submission = create_submission(
        db,
        integration,
        clinic,
    )

    error = RuntimeError("Malaffi unavailable")

    hie_service._mark_submission_failure(
        submission.id,
        error,
    )

    db.session.refresh(submission)

    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Malaffi unavailable"
    assert submission.submitted_at is not None


def test_mark_submission_failure_raises_for_missing_submission(
    app,
):
    with pytest.raises(
        NotFoundError,
        match=r"HIE submission 999999 not found",
    ):
        hie_service._mark_submission_failure(
            999999,
            RuntimeError("failure"),
        )


def test_update_last_sync_updates_integration(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    assert integration.last_sync_at is None

    hie_service._update_last_sync(
        integration.id,
    )

    db.session.refresh(integration)

    assert integration.last_sync_at is not None


def test_update_last_sync_raises_for_missing_integration(
    app,
):
    with pytest.raises(
        NotFoundError,
        match=r"HIE integration 999999 not found",
    ):
        hie_service._update_last_sync(999999)


# ---------------------------------------------------------------------------
# Patient submission
# ---------------------------------------------------------------------------


def test_submit_patient_success(
    db,
    clinic,
    patient,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
    )

    payload = {
        "first_name": patient.first_name,
        "last_name": patient.last_name,
    }

    result = hie_service.submit_patient(
        clinic_id=clinic.id,
        patient_id=patient.id,
        payload=payload,
    )

    assert result["status_code"] == 201
    assert result["external_reference"] == "EXT-PAT-001"

    assert provider.calls == [
        ("submit_patient", payload),
    ]

    submission = HIESubmission.query.one()

    assert submission.integration_id == integration.id
    assert submission.clinic_id == clinic.id
    assert submission.patient_id == patient.id
    assert submission.operation == HIEOperation.PATIENT_SUBMISSION
    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.request_data == payload
    assert submission.response_data == result
    assert submission.status_code == 201
    assert submission.external_reference == "EXT-PAT-001"
    assert submission.submitted_at is not None

    db.session.refresh(integration)

    assert integration.last_sync_at is not None


def test_submit_patient_uses_explicit_integration(
    db,
    clinic,
    patient,
    make_clinic,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    first = create_integration(
        db,
        clinic,
    )

    second = create_integration(
        db,
        clinic,
        endpoint_url="https://second.example",
    )

    result = hie_service.submit_patient(
        clinic_id=clinic.id,
        patient_id=patient.id,
        payload={"mrn": "MRN-001"},
        integration_id=second.id,
    )

    assert result["status_code"] == 201

    submission = HIESubmission.query.one()

    assert submission.integration_id == second.id
    assert submission.integration_id != first.id


def test_submit_patient_rejects_missing_patient(
    db,
    clinic,
    monkeypatch,
):
    fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        NotFoundError,
        match=r"Patient 999999 not found",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=999999,
            payload={"name": "Unknown"},
            integration_id=integration.id,
        )

    assert HIESubmission.query.count() == 0


def test_submit_patient_rejects_cross_clinic_patient(
    db,
    clinic,
    make_clinic,
    make_patient,
    monkeypatch,
):
    fake_provider(monkeypatch)

    other_clinic = make_clinic(
        name="Other Clinic",
    )

    other_patient = make_patient(
        other_clinic,
    )

    integration = create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        ValidationError,
        match="Patient does not belong to the supplied clinic",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=other_patient.id,
            payload={"name": "Cross clinic"},
            integration_id=integration.id,
        )

    assert HIESubmission.query.count() == 0


@pytest.mark.parametrize(
    "status",
    [
        HIEIntegrationStatus.PENDING,
        HIEIntegrationStatus.SUSPENDED,
        HIEIntegrationStatus.DISABLED,
    ],
)
def test_submit_patient_rejects_inactive_integration(
    db,
    clinic,
    patient,
    status,
    monkeypatch,
):
    fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
        status=status,
    )

    with pytest.raises(
        ValidationError,
        match=rf"HIE integration is not active: {status.value}",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"name": "Jane"},
            integration_id=integration.id,
        )

    assert HIESubmission.query.count() == 0


def test_submit_patient_rejects_unsupported_provider(
    db,
    clinic,
    patient,
    monkeypatch,
):
    fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
        provider="fhir",
        status=HIEIntegrationStatus.ACTIVE,
    )

    with pytest.raises(
        ValidationError,
        match="Unsupported HIE provider: fhir",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"name": "Jane"},
            integration_id=integration.id,
        )

    assert HIESubmission.query.count() == 0


def test_submit_patient_marks_submission_failed_when_provider_fails(
    db,
    clinic,
    patient,
    monkeypatch,
):
    class FailingProvider:
        def submit_patient(self, payload):
            raise RuntimeError("Malaffi connection failed")

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: FailingProvider(),
    )

    integration = create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        RuntimeError,
        match="Malaffi connection failed",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"name": "Jane"},
            integration_id=integration.id,
        )

    submission = HIESubmission.query.one()

    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Malaffi connection failed"
    assert submission.submitted_at is not None

    db.session.refresh(integration)

    assert integration.last_sync_at is None


def test_submit_patient_rejects_missing_clinic(
    app,
):
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        hie_service.submit_patient(
            clinic_id=999999,
            patient_id=1,
            payload={"name": "Jane"},
        )


def test_submit_patient_requires_active_default_integration(
    clinic,
    patient,
):
    with pytest.raises(
        ValidationError,
        match="No active Malaffi integration is configured for this clinic",
    ):
        hie_service.submit_patient(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"name": "Jane"},
        )


# ---------------------------------------------------------------------------
# Clinical data submission
# ---------------------------------------------------------------------------


def test_submit_clinical_data_success(
    db,
    clinic,
    patient,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
    )

    payload = {
        "diagnosis": "Hypertension",
        "medications": ["amlodipine"],
    }

    result = hie_service.submit_clinical_data(
        clinic_id=clinic.id,
        patient_id=patient.id,
        payload=payload,
    )

    assert result["status_code"] == 201
    assert provider.calls == [
        ("submit_clinical_data", payload),
    ]

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DATA_SUBMISSION
    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.request_data == payload
    assert submission.response_data == result

    db.session.refresh(integration)

    assert integration.last_sync_at is not None


def test_submit_clinical_data_marks_failure(
    db,
    clinic,
    patient,
    monkeypatch,
):
    class FailingProvider:
        def submit_clinical_data(self, payload):
            raise RuntimeError("Clinical data submission failed")

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: FailingProvider(),
    )

    integration = create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        RuntimeError,
        match="Clinical data submission failed",
    ):
        hie_service.submit_clinical_data(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"diagnosis": "Flu"},
        )

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DATA_SUBMISSION
    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Clinical data submission failed"

    db.session.refresh(integration)

    assert integration.last_sync_at is None


# ---------------------------------------------------------------------------
# Clinical document submission
# ---------------------------------------------------------------------------


def test_submit_clinical_document_success(
    db,
    clinic,
    patient,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
    )

    payload = {
        "document_type": "discharge_summary",
        "content": "Patient discharged in stable condition.",
    }

    result = hie_service.submit_clinical_document(
        clinic_id=clinic.id,
        patient_id=patient.id,
        payload=payload,
    )

    assert result["status_code"] == 201

    assert provider.calls == [
        ("submit_clinical_document", payload),
    ]

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DOCUMENT_SUBMISSION
    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.request_data == payload
    assert submission.response_data == result


def test_submit_clinical_document_marks_failure(
    db,
    clinic,
    patient,
    monkeypatch,
):
    class FailingProvider:
        def submit_clinical_document(self, payload):
            raise RuntimeError("Document submission failed")

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: FailingProvider(),
    )

    create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        RuntimeError,
        match="Document submission failed",
    ):
        hie_service.submit_clinical_document(
            clinic_id=clinic.id,
            patient_id=patient.id,
            payload={"document": "data"},
        )

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DOCUMENT_SUBMISSION
    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Document submission failed"


# ---------------------------------------------------------------------------
# Patient query
# ---------------------------------------------------------------------------


def test_query_patient_success(
    db,
    clinic,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    integration = create_integration(
        db,
        clinic,
    )

    result = hie_service.query_patient(
        clinic_id=clinic.id,
        patient_identifier="MRN-001",
    )

    assert result["status_code"] == 200
    assert result["patient_identifier"] == "MRN-001"

    assert provider.calls == [
        ("query_patient", "MRN-001"),
    ]

    submission = HIESubmission.query.one()

    assert submission.integration_id == integration.id
    assert submission.patient_id is None
    assert submission.operation == HIEOperation.PATIENT_QUERY
    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.request_data == {
        "patient_identifier": "MRN-001",
    }


def test_query_patient_strips_identifier_before_provider_call(
    db,
    clinic,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    create_integration(
        db,
        clinic,
    )

    result = hie_service.query_patient(
        clinic_id=clinic.id,
        patient_identifier="  MRN-001  ",
    )

    assert result["patient_identifier"] == "MRN-001"

    assert provider.calls == [
        ("query_patient", "MRN-001"),
    ]

    submission = HIESubmission.query.one()

    assert submission.request_data == {
        "patient_identifier": "  MRN-001  ",
    }


def test_query_patient_marks_failure(
    db,
    clinic,
    monkeypatch,
):
    class FailingProvider:
        def query_patient(self, patient_identifier):
            raise RuntimeError("Patient query failed")

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: FailingProvider(),
    )

    create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        RuntimeError,
        match="Patient query failed",
    ):
        hie_service.query_patient(
            clinic_id=clinic.id,
            patient_identifier="MRN-001",
        )

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.PATIENT_QUERY
    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Patient query failed"


# ---------------------------------------------------------------------------
# Clinical data query
# ---------------------------------------------------------------------------


def test_query_clinical_data_success_without_filters(
    db,
    clinic,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    create_integration(
        db,
        clinic,
    )

    result = hie_service.query_clinical_data(
        clinic_id=clinic.id,
        patient_identifier="MRN-001",
    )

    assert result["status_code"] == 200
    assert result["patient_identifier"] == "MRN-001"
    assert result["filters"] is None

    assert provider.calls == [
        (
            "query_clinical_data",
            "MRN-001",
            None,
        ),
    ]

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DATA_QUERY
    assert submission.status == HIESubmissionStatus.SUCCESS
    assert submission.request_data == {
        "patient_identifier": "MRN-001",
        "filters": None,
    }


def test_query_clinical_data_passes_filters(
    db,
    clinic,
    monkeypatch,
):
    provider = fake_provider(monkeypatch)

    create_integration(
        db,
        clinic,
    )

    filters = {
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
        "domain": "lab",
    }

    result = hie_service.query_clinical_data(
        clinic_id=clinic.id,
        patient_identifier="MRN-001",
        filters=filters,
    )

    assert result["filters"] == filters

    assert provider.calls == [
        (
            "query_clinical_data",
            "MRN-001",
            filters,
        ),
    ]

    submission = HIESubmission.query.one()

    assert submission.request_data == {
        "patient_identifier": "MRN-001",
        "filters": filters,
    }


def test_query_clinical_data_marks_failure(
    db,
    clinic,
    monkeypatch,
):
    class FailingProvider:
        def query_clinical_data(
            self,
            patient_identifier,
            filters=None,
        ):
            raise RuntimeError("Clinical query failed")

    monkeypatch.setattr(
        hie_service,
        "MalaffiProvider",
        lambda endpoint=None: FailingProvider(),
    )

    create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        RuntimeError,
        match="Clinical query failed",
    ):
        hie_service.query_clinical_data(
            clinic_id=clinic.id,
            patient_identifier="MRN-001",
        )

    submission = HIESubmission.query.one()

    assert submission.operation == HIEOperation.CLINICAL_DATA_QUERY
    assert submission.status == HIESubmissionStatus.FAILED
    assert submission.error_message == "Clinical query failed"


# ---------------------------------------------------------------------------
# Integration CRUD
# ---------------------------------------------------------------------------


def test_create_hie_integration_uses_defaults(
    db,
    clinic,
):
    integration = hie_service.create_hie_integration(
        clinic_id=clinic.id,
    )

    assert integration.id is not None
    assert integration.clinic_id == clinic.id
    assert integration.provider == "malaffi"
    assert integration.status == HIEIntegrationStatus.PENDING
    assert integration.endpoint_url is None
    assert integration.organization_id is None
    assert integration.facility_id is None


def test_create_hie_integration_normalizes_provider(
    clinic,
):
    integration = hie_service.create_hie_integration(
        clinic_id=clinic.id,
        provider="  MALAFFI  ",
    )

    assert integration.provider == "malaffi"


def test_create_hie_integration_preserves_optional_fields(
    clinic,
):
    integration = hie_service.create_hie_integration(
        clinic_id=clinic.id,
        provider="malaffi",
        endpoint_url="https://malaffi.example",
        organization_id="ORG-100",
        facility_id="FAC-100",
    )

    assert integration.endpoint_url == "https://malaffi.example"
    assert integration.organization_id == "ORG-100"
    assert integration.facility_id == "FAC-100"
    assert integration.status == HIEIntegrationStatus.PENDING


def test_create_hie_integration_rejects_empty_provider(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Provider is required",
    ):
        hie_service.create_hie_integration(
            clinic_id=clinic.id,
            provider="   ",
        )


def test_create_hie_integration_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        hie_service.create_hie_integration(
            clinic_id=999999,
        )


def test_get_hie_integration_returns_integration(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    result = hie_service.get_hie_integration(
        clinic_id=clinic.id,
        integration_id=integration.id,
    )

    assert result.id == integration.id


def test_get_hie_integration_rejects_wrong_clinic(
    db,
    clinic,
    make_clinic,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    integration = create_integration(
        db,
        other_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="HIE integration does not belong to the supplied clinic",
    ):
        hie_service.get_hie_integration(
            clinic_id=clinic.id,
            integration_id=integration.id,
        )


def test_update_hie_integration_updates_all_supplied_fields(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        endpoint_url="https://old.example",
        organization_id="OLD-ORG",
        facility_id="OLD-FAC",
    )

    updated = hie_service.update_hie_integration(
        clinic_id=clinic.id,
        integration_id=integration.id,
        provider="  MALAFFI  ",
        status=HIEIntegrationStatus.SUSPENDED,
        endpoint_url="https://new.example",
        organization_id="NEW-ORG",
        facility_id="NEW-FAC",
    )

    assert updated.provider == "malaffi"
    assert updated.status == HIEIntegrationStatus.SUSPENDED
    assert updated.endpoint_url == "https://new.example"
    assert updated.organization_id == "NEW-ORG"
    assert updated.facility_id == "NEW-FAC"


def test_update_hie_integration_updates_only_supplied_fields(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
        endpoint_url="https://original.example",
        organization_id="ORG-001",
        facility_id="FAC-001",
    )

    updated = hie_service.update_hie_integration(
        clinic_id=clinic.id,
        integration_id=integration.id,
        status=HIEIntegrationStatus.ACTIVE,
    )

    assert updated.status == HIEIntegrationStatus.ACTIVE
    assert updated.endpoint_url == "https://original.example"
    assert updated.organization_id == "ORG-001"
    assert updated.facility_id == "FAC-001"


def test_update_hie_integration_rejects_empty_provider(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    with pytest.raises(
        ValidationError,
        match="Provider cannot be empty",
    ):
        hie_service.update_hie_integration(
            clinic_id=clinic.id,
            integration_id=integration.id,
            provider="   ",
        )


def test_update_hie_integration_rejects_missing_integration(
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match=r"HIE integration 999999 not found",
    ):
        hie_service.update_hie_integration(
            clinic_id=clinic.id,
            integration_id=999999,
            status=HIEIntegrationStatus.ACTIVE,
        )


# ---------------------------------------------------------------------------
# Submission listing
# ---------------------------------------------------------------------------


def test_list_hie_submissions_returns_paginated_results(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    for index in range(3):
        create_submission(
            db,
            integration,
            clinic,
            patient_id=patient.id,
            operation=HIEOperation.PATIENT_SUBMISSION,
            request_data={"index": index},
        )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
    )

    assert pagination.total == 3
    assert pagination.page == 1
    assert pagination.per_page == 20
    assert len(pagination.items) == 3


def test_list_hie_submissions_filters_by_integration(
    db,
    clinic,
    patient,
):
    first = create_integration(
        db,
        clinic,
    )

    second = create_integration(
        db,
        clinic,
        endpoint_url="https://second.example",
    )

    first_submission = create_submission(
        db,
        first,
        clinic,
        patient_id=patient.id,
    )

    create_submission(
        db,
        second,
        clinic,
        patient_id=patient.id,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        integration_id=first.id,
    )

    assert pagination.total == 1
    assert pagination.items[0].id == first_submission.id


def test_list_hie_submissions_filters_by_patient(
    db,
    clinic,
    patient,
    make_patient,
):
    other_patient = make_patient(
        clinic,
    )

    integration = create_integration(
        db,
        clinic,
    )

    patient_submission = create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=other_patient.id,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        patient_id=patient.id,
    )

    assert pagination.total == 1
    assert pagination.items[0].id == patient_submission.id


def test_list_hie_submissions_filters_by_operation(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    patient_submission = create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_SUBMISSION,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        operation=HIEOperation.PATIENT_SUBMISSION,
    )

    assert pagination.total == 1
    assert pagination.items[0].id == patient_submission.id


def test_list_hie_submissions_filters_by_status(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    success_submission = create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        status=HIESubmissionStatus.SUCCESS,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        status=HIESubmissionStatus.FAILED,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        status=HIESubmissionStatus.SUCCESS,
    )

    assert pagination.total == 1
    assert pagination.items[0].id == success_submission.id


def test_list_hie_submissions_combines_filters(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    matching = create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_QUERY,
        status=HIESubmissionStatus.SUCCESS,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_QUERY,
        status=HIESubmissionStatus.FAILED,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.CLINICAL_DATA_QUERY,
        status=HIESubmissionStatus.SUCCESS,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        integration_id=integration.id,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_QUERY,
        status=HIESubmissionStatus.SUCCESS,
    )

    assert pagination.total == 1
    assert pagination.items[0].id == matching.id


def test_list_hie_submissions_paginates(
    db,
    clinic,
    patient,
):
    integration = create_integration(
        db,
        clinic,
    )

    for index in range(5):
        create_submission(
            db,
            integration,
            clinic,
            patient_id=patient.id,
            request_data={"index": index},
        )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        page=2,
        per_page=2,
    )

    assert pagination.total == 5
    assert pagination.page == 2
    assert pagination.per_page == 2
    assert len(pagination.items) == 2


def test_list_hie_submissions_returns_empty_for_no_matches(
    db,
    clinic,
):
    integration = create_integration(
        db,
        clinic,
    )

    create_submission(
        db,
        integration,
        clinic,
    )

    pagination = hie_service.list_hie_submissions(
        clinic_id=clinic.id,
        operation=HIEOperation.CLINICAL_DATA_QUERY,
    )

    assert pagination.total == 0
    assert pagination.items == []


def test_list_hie_submissions_rejects_missing_clinic():
    with pytest.raises(
        NotFoundError,
        match=r"Clinic 999999 not found",
    ):
        hie_service.list_hie_submissions(
            clinic_id=999999,
        )