from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.modules.hie.routes import hie_route


def make_integration(
    *,
    integration_id=1,
    clinic_id=1,
    provider="malaffi",
    status=HIEIntegrationStatus.PENDING,
    endpoint_url=None,
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
    external_reference=None,
    request_data=None,
    response_data=None,
    status_code=None,
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
        external_reference=external_reference,
        request_data=request_data,
        response_data=response_data,
        status_code=status_code,
        error_message=error_message,
        retry_count=retry_count,
        submitted_at=submitted_at,
        created_at=now,
        updated_at=now,
    )


def make_pagination(
    items,
    *,
    total=None,
    page=1,
    per_page=20,
):
    return SimpleNamespace(
        items=items,
        total=len(items) if total is None else total,
        page=page,
        per_page=per_page,
    )


def test_create_integration_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        clinic_id=clinic.id,
        provider="malaffi",
        status=HIEIntegrationStatus.PENDING,
        endpoint_url="https://hie.example.com/",
    )

    called = {}

    def fake_create_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "create_hie_integration",
        fake_create_hie_integration,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "MALAFFI",
            "endpoint_url": "https://hie.example.com",
            "organization_id": " ORG-001 ",
            "facility_id": " FAC-001 ",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == integration.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["provider"] == "malaffi"
    assert body["data"]["status"] == (
        HIEIntegrationStatus.PENDING.value
    )
    assert body["data"]["endpoint_url"] == (
        "https://hie.example.com/"
    )

    assert called["clinic_id"] == clinic.id
    assert called["provider"] == "malaffi"
    assert called["endpoint_url"] == (
        "https://hie.example.com/"
    )
    assert called["organization_id"] == "ORG-001"
    assert called["facility_id"] == "FAC-001"


def test_create_integration_uses_authenticated_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        clinic_id=clinic.id,
    )

    called = {}

    def fake_create_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "create_hie_integration",
        fake_create_hie_integration,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "malaffi",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert called["clinic_id"] == clinic.id


def test_create_integration_rejects_client_clinic_id(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "malaffi",
            "clinic_id": 999999,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_integration_defaults_provider_to_malaffi(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        clinic_id=clinic.id,
        provider="malaffi",
    )

    called = {}

    def fake_create_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "create_hie_integration",
        fake_create_hie_integration,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={},
        headers=headers,
    )

    assert response.status_code == 201
    assert called["provider"] == "malaffi"


def test_create_integration_rejects_unknown_field(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "malaffi",
            "unknown_field": "bad",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_integration_rejects_invalid_provider(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_integration_rejects_invalid_endpoint(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "endpoint_url": "not-a-url",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_integration_rejects_empty_identifier(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "organization_id": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_integration_forbidden_for_doctor(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.DOCTOR,
    )

    response = app.test_client().post(
        "/api/hie/integrations",
        json={
            "provider": "malaffi",
        },
        headers=headers,
    )

    assert response.status_code == 403


def test_get_integration_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        integration_id=7,
        clinic_id=clinic.id,
        status=HIEIntegrationStatus.ACTIVE,
    )

    called = {}

    def fake_get_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "get_hie_integration",
        fake_get_hie_integration,
    )

    response = app.test_client().get(
        "/api/hie/integrations/7",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 7
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["provider"] == "malaffi"
    assert body["data"]["status"] == (
        HIEIntegrationStatus.ACTIVE.value
    )

    assert called["integration_id"] == 7
    assert called["clinic_id"] == clinic.id


def test_get_integration_uses_authenticated_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.DOCTOR,
    )

    integration = make_integration(
        integration_id=15,
        clinic_id=clinic.id,
    )

    called = {}

    def fake_get_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "get_hie_integration",
        fake_get_hie_integration,
    )

    response = app.test_client().get(
        "/api/hie/integrations/15",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["integration_id"] == 15
    assert called["clinic_id"] == clinic.id


def test_update_integration_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        integration_id=5,
        clinic_id=clinic.id,
        provider="malaffi",
        status=HIEIntegrationStatus.ACTIVE,
        endpoint_url="https://hie.example.com/",
        organization_id="ORG-NEW",
        facility_id="FAC-NEW",
    )

    called = {}

    def fake_update_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "update_hie_integration",
        fake_update_hie_integration,
    )

    response = app.test_client().patch(
        "/api/hie/integrations/5",
        json={
            "provider": "MALAFFI",
            "status": HIEIntegrationStatus.ACTIVE.value,
            "endpoint_url": "https://hie.example.com",
            "organization_id": "ORG-NEW",
            "facility_id": "FAC-NEW",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 5
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["status"] == (
        HIEIntegrationStatus.ACTIVE.value
    )

    assert called["clinic_id"] == clinic.id
    assert called["integration_id"] == 5
    assert called["provider"] == "malaffi"
    assert called["status"] == HIEIntegrationStatus.ACTIVE
    assert called["endpoint_url"] == (
        "https://hie.example.com/"
    )
    assert called["organization_id"] == "ORG-NEW"
    assert called["facility_id"] == "FAC-NEW"


def test_update_integration_forbidden_for_nurse(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.NURSE,
    )

    response = app.test_client().patch(
        "/api/hie/integrations/1",
        json={
            "status": HIEIntegrationStatus.ACTIVE.value,
        },
        headers=headers,
    )

    assert response.status_code == 403


def test_update_integration_normalizes_provider(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    integration = make_integration(
        clinic_id=clinic.id,
        provider="malaffi",
    )

    called = {}

    def fake_update_hie_integration(**kwargs):
        called.update(kwargs)
        return integration

    monkeypatch.setattr(
        hie_route,
        "update_hie_integration",
        fake_update_hie_integration,
    )

    response = app.test_client().patch(
        "/api/hie/integrations/1",
        json={
            "provider": "  MALAFFI  ",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert called["provider"] == "malaffi"


def test_update_integration_rejects_unknown_field(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().patch(
        "/api/hie/integrations/1",
        json={
            "unknown_field": "bad",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    submissions = [
        make_submission(
            submission_id=1,
            integration_id=10,
            clinic_id=clinic.id,
            operation=HIEOperation.PATIENT_SUBMISSION,
            status=HIESubmissionStatus.SUCCESS,
        ),
        make_submission(
            submission_id=2,
            integration_id=10,
            clinic_id=clinic.id,
            operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
            status=HIESubmissionStatus.FAILED,
        ),
    ]

    called = {}

    def fake_list_hie_submissions(**kwargs):
        called.update(kwargs)
        return make_pagination(
            submissions,
            total=2,
            page=1,
            per_page=20,
        )

    monkeypatch.setattr(
        hie_route,
        "list_hie_submissions",
        fake_list_hie_submissions,
    )

    response = app.test_client().get(
        "/api/hie/submissions",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 20
    assert len(body["data"]["items"]) == 2

    assert called["clinic_id"] == clinic.id
    assert called["integration_id"] is None
    assert called["patient_id"] is None
    assert called["operation"] is None
    assert called["status"] is None
    assert called["page"] == 1
    assert called["per_page"] == 20


def test_get_submissions_passes_filters(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.DOCTOR,
    )

    called = {}

    def fake_list_hie_submissions(**kwargs):
        called.update(kwargs)

        return make_pagination(
            [],
            total=0,
            page=2,
            per_page=10,
        )

    monkeypatch.setattr(
        hie_route,
        "list_hie_submissions",
        fake_list_hie_submissions,
    )

    response = app.test_client().get(
        "/api/hie/submissions"
        "?integration_id=5"
        "&patient_id=8"
        f"&operation={HIEOperation.PATIENT_QUERY.value}"
        f"&status={HIESubmissionStatus.SUCCESS.value}"
        "&page=2"
        "&per_page=10",
        headers=headers,
    )

    assert response.status_code == 200

    assert called["clinic_id"] == clinic.id
    assert called["integration_id"] == 5
    assert called["patient_id"] == 8
    assert called["operation"] == HIEOperation.PATIENT_QUERY
    assert called["status"] == HIESubmissionStatus.SUCCESS
    assert called["page"] == 2
    assert called["per_page"] == 10


def test_get_submissions_uses_authenticated_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.PHARMACIST,
    )

    called = {}

    def fake_list_hie_submissions(**kwargs):
        called.update(kwargs)
        return make_pagination([])

    monkeypatch.setattr(
        hie_route,
        "list_hie_submissions",
        fake_list_hie_submissions,
    )

    response = app.test_client().get(
        "/api/hie/submissions",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["clinic_id"] == clinic.id


def test_get_submissions_rejects_invalid_integration_id(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        "/api/hie/submissions?integration_id=0",
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_rejects_invalid_patient_id(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        "/api/hie/submissions?patient_id=0",
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "page",
    ["0", "-1", "abc"],
)
def test_get_submissions_rejects_invalid_page(
    app,
    auth_headers_for,
    user,
    page,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        f"/api/hie/submissions?page={page}",
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "per_page",
    ["0", "-1", "101", "abc"],
)
def test_get_submissions_rejects_invalid_per_page(
    app,
    auth_headers_for,
    user,
    per_page,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        f"/api/hie/submissions?per_page={per_page}",
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_accepts_maximum_per_page(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    called = {}

    def fake_list_hie_submissions(**kwargs):
        called.update(kwargs)
        return make_pagination(
            [],
            total=0,
            page=1,
            per_page=100,
        )

    monkeypatch.setattr(
        hie_route,
        "list_hie_submissions",
        fake_list_hie_submissions,
    )

    response = app.test_client().get(
        "/api/hie/submissions?per_page=100",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["per_page"] == 100


def test_get_submissions_rejects_invalid_operation(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        "/api/hie/submissions?operation=invalid",
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_rejects_invalid_status(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        "/api/hie/submissions?status=invalid",
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_rejects_unknown_field(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    response = app.test_client().get(
        "/api/hie/submissions?unknown_field=bad",
        headers=headers,
    )

    assert response.status_code == 422


def test_get_submissions_serializes_submission_fields(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    submitted_at = datetime.now(timezone.utc)

    submission = make_submission(
        submission_id=55,
        integration_id=8,
        clinic_id=clinic.id,
        patient_id=12,
        operation=HIEOperation.PATIENT_QUERY,
        status=HIESubmissionStatus.SUCCESS,
        external_reference="EXT-55",
        request_data={
            "patient_identifier": "MRN-55",
        },
        response_data={
            "status_code": 200,
        },
        status_code=200,
        retry_count=1,
        submitted_at=submitted_at,
    )

    monkeypatch.setattr(
        hie_route,
        "list_hie_submissions",
        lambda **kwargs: make_pagination(
            [submission],
            total=1,
            page=1,
            per_page=20,
        ),
    )

    response = app.test_client().get(
        "/api/hie/submissions",
        headers=headers,
    )

    assert response.status_code == 200

    item = response.get_json()["data"]["items"][0]

    assert item["id"] == 55
    assert item["integration_id"] == 8
    assert item["clinic_id"] == clinic.id
    assert item["patient_id"] == 12
    assert item["operation"] == (
        HIEOperation.PATIENT_QUERY.value
    )
    assert item["status"] == (
        HIESubmissionStatus.SUCCESS.value
    )
    assert item["external_reference"] == "EXT-55"
    assert item["request_data"] == {
        "patient_identifier": "MRN-55",
    }
    assert item["response_data"] == {
        "status_code": 200,
    }
    assert item["status_code"] == 200
    assert item["retry_count"] == 1
    assert item["submitted_at"] is not None


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/hie/integrations"),
        ("get", "/api/hie/integrations/1"),
        ("patch", "/api/hie/integrations/1"),
        ("get", "/api/hie/submissions"),
    ],
)
def test_hie_routes_require_authentication(
    app,
    method,
    path,
):
    client = app.test_client()

    response = getattr(client, method)(
        path
    )

    assert response.status_code in (401, 422)


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.LAB_TECHNICIAN,
        Role.PHARMACIST,
    ],
)
def test_get_integration_allowed_for_hie_view_roles(
    app,
    clinic,
    auth_headers_for,
    make_user,
    role,
    monkeypatch,
):
    view_user = make_user(
        clinic,
        role=role,
    )

    headers = auth_headers_for(
        view_user,
        role=role,
    )

    integration = make_integration(
        integration_id=3,
        clinic_id=clinic.id,
    )

    monkeypatch.setattr(
        hie_route,
        "get_hie_integration",
        lambda **kwargs: integration,
    )

    response = app.test_client().get(
        "/api/hie/integrations/3",
        headers=headers,
    )

    assert response.status_code == 200


def test_get_integration_forbidden_for_patient(
    app,
    clinic,
    auth_headers_for,
    make_user,
):
    patient_user = make_user(
        clinic,
        role=Role.PATIENT,
    )

    headers = auth_headers_for(
        patient_user,
        role=Role.PATIENT,
    )

    response = app.test_client().get(
        "/api/hie/integrations/1",
        headers=headers,
    )

    assert response.status_code == 403


def test_domain_validation_error_is_handled(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(
        user,
        role=Role.ADMIN,
    )

    def fake_get_hie_integration(**kwargs):
        raise ValidationError(
            "HIE integration not found"
        )

    monkeypatch.setattr(
        hie_route,
        "get_hie_integration",
        fake_get_hie_integration,
    )

    response = app.test_client().get(
        "/api/hie/integrations/999",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "HIE integration not found"