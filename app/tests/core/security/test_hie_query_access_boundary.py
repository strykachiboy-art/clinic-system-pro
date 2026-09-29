from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.hie_enums import HIEIntegrationStatus
from app.modules.hie.services import hie_service


def _make_integration(
    clinic_id: int,
    integration_id: int = 1,
):
    return SimpleNamespace(
        id=integration_id,
        clinic_id=clinic_id,
        provider="malaffi",
        status=HIEIntegrationStatus.ACTIVE,
        endpoint_url="https://hie.example.com",
        organization_id="ORG-001",
        facility_id="FAC-001",
    )


def _prepare_hie_query(
    monkeypatch,
    clinic_id: int,
):
    integration = _make_integration(
        clinic_id=clinic_id,
    )

    provider = Mock()

    monkeypatch.setattr(
        hie_service,
        "_get_clinic",
        Mock(),
    )

    monkeypatch.setattr(
        hie_service,
        "_get_integration",
        Mock(
            return_value=integration,
        ),
    )

    monkeypatch.setattr(
        hie_service,
        "_validate_integration",
        Mock(),
    )

    monkeypatch.setattr(
        hie_service,
        "_get_provider",
        Mock(
            return_value=provider,
        ),
    )

    monkeypatch.setattr(
        hie_service,
        "_create_submission",
        Mock(
            return_value=100,
        ),
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

    return provider


def test_hie_patient_query_accepts_arbitrary_external_identifier_without_authorization_context(
    monkeypatch,
):
    provider = _prepare_hie_query(
        monkeypatch,
        clinic_id=1,
    )

    provider.query_patient.return_value = {
        "status_code": 200,
        "records": [],
    }

    result = hie_service.query_patient(
        clinic_id=1,
        patient_identifier="EXTERNAL-PATIENT-999999",
    )

    assert result["status_code"] == 200

    provider.query_patient.assert_called_once_with(
        "EXTERNAL-PATIENT-999999",
    )

    hie_service._create_submission.assert_called_once()


def test_hie_clinical_query_accepts_arbitrary_external_identifier_without_authorization_context(
    monkeypatch,
):
    provider = _prepare_hie_query(
        monkeypatch,
        clinic_id=1,
    )

    provider.query_clinical_data.return_value = {
        "status_code": 200,
        "records": [
            {
                "id": "REMOTE-RECORD-1",
            },
        ],
    }

    result = hie_service.query_clinical_data(
        clinic_id=1,
        patient_identifier="EXTERNAL-PATIENT-999999",
        filters={
            "resource_type": "Medication",
        },
    )

    assert result["status_code"] == 200

    provider.query_clinical_data.assert_called_once_with(
        "EXTERNAL-PATIENT-999999",
        {
            "resource_type": "Medication",
        },
    )

    hie_service._create_submission.assert_called_once()