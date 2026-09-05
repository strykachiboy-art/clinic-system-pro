import pytest

from app.core.enums.role_enums import Role

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.modules.hie.models.hie_model import (
    HIEIntegration,
    HIESubmission,
)


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


# ---------------------------------------------------------------------------
# Create integration
# ---------------------------------------------------------------------------


def test_create_integration_success(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": clinic.id,
            "provider": "malaffi",
            "endpoint_url": "https://malaffi.example",
            "organization_id": "ORG-001",
            "facility_id": "FAC-001",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["provider"] == "malaffi"
    assert body["data"]["status"] == "pending"
    assert body["data"]["endpoint_url"] == "https://malaffi.example"
    assert body["data"]["organization_id"] == "ORG-001"
    assert body["data"]["facility_id"] == "FAC-001"

    integration = HIEIntegration.query.one()

    assert integration.provider == "malaffi"
    assert integration.status == HIEIntegrationStatus.PENDING


def test_create_integration_uses_provider_default(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": clinic.id,
        },
    )

    assert response.status_code == 201

    data = response.get_json()["data"]

    assert data["provider"] == "malaffi"
    assert data["status"] == "pending"


def test_create_integration_normalizes_provider(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": clinic.id,
            "provider": "  MALAFFI  ",
        },
    )

    assert response.status_code == 201

    assert response.get_json()["data"]["provider"] == "malaffi"


def test_create_integration_rejects_invalid_clinic_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": 0,
        },
    )

    assert response.status_code == 422


def test_create_integration_rejects_missing_clinic(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": 999999,
        },
    )

    assert response.status_code == 404


def test_create_integration_rejects_empty_provider(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": clinic.id,
            "provider": "   ",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.LAB_TECHNICIAN,
        Role.PHARMACIST,
    ],
)
def test_create_integration_forbidden_for_non_admin_roles(
    client,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    response = client.post(
        "/api/hie/integrations",
        headers=auth_headers_for(
            actor,
            role=role,
        ),
        json={
            "clinic_id": clinic.id,
        },
    )

    assert response.status_code == 403


def test_create_integration_requires_authentication(
    client,
    clinic,
):
    response = client.post(
        "/api/hie/integrations",
        json={
            "clinic_id": clinic.id,
        },
    )

    assert response.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Get integration
# ---------------------------------------------------------------------------


def test_get_integration_success(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
        status=HIEIntegrationStatus.ACTIVE,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["id"] == integration.id
    assert data["clinic_id"] == clinic.id
    assert data["provider"] == "malaffi"
    assert data["status"] == "active"


def test_get_integration_requires_clinic_id(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/hie/integrations/{integration.id}",
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id query parameter is required"


def test_get_integration_returns_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/integrations/999999",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 404


def test_get_integration_rejects_wrong_clinic(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    auth_headers_for,
):
    other_clinic = make_clinic(
        name="Other HIE Clinic",
    )

    integration = create_integration(
        db,
        other_clinic,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "HIE integration does not belong to the supplied clinic"
    )


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
        Role.LAB_TECHNICIAN,
        Role.PHARMACIST,
    ],
)
def test_get_integration_allowed_roles(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=role,
    )

    response = client.get(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=role,
        ),
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Update integration
# ---------------------------------------------------------------------------


def test_update_integration_success(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
        status=HIEIntegrationStatus.PENDING,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "provider": "MALAFFI",
            "status": "active",
            "endpoint_url": "https://new.example",
            "organization_id": "ORG-NEW",
            "facility_id": "FAC-NEW",
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["provider"] == "malaffi"
    assert data["status"] == "active"
    assert data["endpoint_url"] == "https://new.example"
    assert data["organization_id"] == "ORG-NEW"
    assert data["facility_id"] == "FAC-NEW"


def test_update_integration_can_get_clinic_id_from_query(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "status": "suspended",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "suspended"


def test_update_integration_can_get_clinic_id_from_body(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "clinic_id": clinic.id,
            "status": "active",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "active"


def test_update_integration_requires_clinic_id(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "status": "active",
        },
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id is required"


def test_update_integration_rejects_empty_provider(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "provider": "   ",
        },
    )

    assert response.status_code == 422


def test_update_integration_rejects_invalid_status(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "status": "invalid",
        },
    )

    assert response.status_code == 422


def test_update_integration_returns_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        "/api/hie/integrations/999999",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "status": "active",
        },
    )

    assert response.status_code == 404


def test_update_integration_rejects_wrong_clinic(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    auth_headers_for,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    integration = create_integration(
        db,
        other_clinic,
    )

    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.ADMIN,
        ),
        json={
            "status": "active",
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "HIE integration does not belong to the supplied clinic"
    )


@pytest.mark.parametrize(
    "role",
    [
        Role.DOCTOR,
        Role.NURSE,
        Role.LAB_TECHNICIAN,
        Role.PHARMACIST,
    ],
)
def test_update_integration_forbidden_for_non_admin_roles(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    integration = create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=role,
    )

    response = client.patch(
        f"/api/hie/integrations/{integration.id}",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=role,
        ),
        json={
            "status": "active",
        },
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


def test_get_submissions_requires_clinic_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 400

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id query parameter is required"


def test_get_submissions_success(
    client,
    db,
    clinic,
    patient,
    make_user,
    auth_headers_for,
):
    integration = create_integration(
        db,
        clinic,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.PATIENT_SUBMISSION,
        status=HIESubmissionStatus.SUCCESS,
        request_data={
            "first_name": "Jane",
        },
        response_data={
            "status_code": 201,
        },
        external_reference="EXT-001",
        status_code=201,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 20
    assert len(body["data"]["items"]) == 1


def test_get_submissions_filters_by_integration(
    client,
    db,
    clinic,
    patient,
    make_user,
    auth_headers_for,
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

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "integration_id": integration_id_to_string(first.id),
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == first_submission.id


def test_get_submissions_filters_by_patient(
    client,
    db,
    clinic,
    patient,
    make_patient,
    make_user,
    auth_headers_for,
):
    other_patient = make_patient(
        clinic,
    )

    integration = create_integration(
        db,
        clinic,
    )

    matching = create_submission(
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

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "patient_id": patient.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == matching.id


def test_get_submissions_filters_by_operation(
    client,
    db,
    clinic,
    patient,
    make_user,
    auth_headers_for,
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
        operation=HIEOperation.PATIENT_SUBMISSION,
    )

    create_submission(
        db,
        integration,
        clinic,
        patient_id=patient.id,
        operation=HIEOperation.CLINICAL_DATA_SUBMISSION,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "operation": HIEOperation.PATIENT_SUBMISSION.value,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    items = response.get_json()["data"]["items"]

    assert len(items) == 1
    assert items[0]["id"] == matching.id


def test_get_submissions_paginates(
    client,
    db,
    clinic,
    patient,
    make_user,
    auth_headers_for,
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
            request_data={
                "index": index,
            },
        )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "page": 2,
            "per_page": 2,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["total"] == 5
    assert data["page"] == 2
    assert data["per_page"] == 2
    assert len(data["items"]) == 2


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
        Role.LAB_TECHNICIAN,
        Role.PHARMACIST,
    ],
)
def test_get_submissions_allowed_roles(
    client,
    db,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    create_integration(
        db,
        clinic,
    )

    actor = make_user(
        clinic,
        role=role,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=role,
        ),
    )

    assert response.status_code == 200


def test_get_submissions_rejects_invalid_integration_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "integration_id": 0,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422


def test_get_submissions_rejects_invalid_patient_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "patient_id": 0,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422


def test_get_submissions_rejects_invalid_operation(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "operation": "invalid_operation",
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422


def test_get_submissions_rejects_invalid_page(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "page": 0,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422


def test_get_submissions_rejects_per_page_above_limit(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
            "per_page": 101,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 422


def test_get_submissions_rejects_missing_authentication(
    client,
    clinic,
):
    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
        },
    )

    assert response.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Route-level isolation / clinic behavior
# ---------------------------------------------------------------------------


def test_get_submissions_does_not_return_other_clinic_records(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    auth_headers_for,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    integration = create_integration(
        db,
        other_clinic,
    )

    other_submission = create_submission(
        db,
        integration,
        other_clinic,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    create_integration(
        db,
        clinic,
    )

    response = client.get(
        "/api/hie/submissions",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(
            actor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["total"] == 0
    assert all(
        item["id"] != other_submission.id
        for item in data["items"]
    )


# ---------------------------------------------------------------------------
# Small compatibility helper
# ---------------------------------------------------------------------------


def integration_id_to_string(value):
    return str(value)


