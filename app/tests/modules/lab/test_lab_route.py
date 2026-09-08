from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.lab_enums import (
    LabOrderStatus,
    LabResultFlag,
    SampleType,
)
from app.core.enums.role_enums import Role


@pytest.fixture
def lab_routes():
    import app.modules.lab.routes.lab_route as routes

    return routes


@pytest.fixture
def lab_admin_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(clinic, Role.ADMIN)


@pytest.fixture
def lab_admin_headers(lab_admin_context):
    _, headers = lab_admin_context
    return headers


@pytest.fixture
def lab_admin_staff(lab_admin_context):
    staff, _ = lab_admin_context
    return staff


@pytest.fixture
def lab_technician_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(clinic, Role.LAB_TECHNICIAN)


@pytest.fixture
def lab_technician_headers(lab_technician_context):
    _, headers = lab_technician_context
    return headers


@pytest.fixture
def lab_doctor_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(clinic, Role.DOCTOR)


@pytest.fixture
def lab_doctor_headers(lab_doctor_context):
    _, headers = lab_doctor_context
    return headers


@pytest.fixture
def lab_receptionist_context(make_authenticated_staff, clinic):
    return make_authenticated_staff(clinic, Role.RECEPTIONIST)


@pytest.fixture
def lab_receptionist_headers(lab_receptionist_context):
    _, headers = lab_receptionist_context
    return headers


def test_obj(**overrides):
    values = dict(
        id=1,
        clinic_id=1,
        loinc_code="12345-6",
        name="CBC",
        code="CBC",
        sample_type=SampleType.BLOOD,
        reference_range="5 - 20",
        unit="mg/dL",
        price=Decimal("25.00"),
        critical_low=Decimal("2.000"),
        critical_high=Decimal("40.000"),
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def item_obj(**overrides):
    test = overrides.pop("test", test_obj())
    values = dict(
        id=1,
        order_id=1,
        test_id=test.id,
        test=test,
        result_value="10",
        flag=LabResultFlag.NORMAL,
        result_notes="Normal",
        result_file_url=None,
        resulted_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def order_obj(**overrides):
    values = dict(
        id=1,
        clinic_id=1,
        patient_id=10,
        consultation_id=None,
        ordered_by_id=1,
        collected_by_id=2,
        processed_by_id=3,
        verified_by_id=4,
        status=LabOrderStatus.IN_PROGRESS,
        qr_code="LAB-123",
        sample_collected_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc),
        verified_at=None,
        completed_at=None,
        equipment_reference_id=None,
        cancellation_reason=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        items=[item_obj()],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


# ============================================================================
# HELPERS / SERIALIZERS
# ============================================================================


def test_current_user_resolves_jwt_user(
    lab_routes,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        lab_routes,
        "get_jwt_identity",
        Mock(return_value=str(user.id)),
    )

    assert lab_routes._get_current_user() is user


def test_current_user_rejects_invalid_identity(
    lab_routes,
    monkeypatch,
):
    from app.core.exceptions import ValidationError

    monkeypatch.setattr(
        lab_routes,
        "get_jwt_identity",
        Mock(return_value="not-an-int"),
    )

    with pytest.raises(
        ValidationError,
        match="Invalid authentication identity",
    ):
        lab_routes._get_current_user()


def test_current_user_rejects_missing_user(
    lab_routes,
    monkeypatch,
):
    from app.core.exceptions import ValidationError

    monkeypatch.setattr(
        lab_routes,
        "get_jwt_identity",
        Mock(return_value="999999"),
    )
    monkeypatch.setattr(
        lab_routes.db.session,
        "get",
        Mock(return_value=None),
    )

    with pytest.raises(
        ValidationError,
        match="could not be resolved",
    ):
        lab_routes._get_current_user()


def test_current_staff_uses_authenticated_staff(
    lab_routes,
    lab_admin_staff,
    monkeypatch,
):
    monkeypatch.setattr(
        lab_routes,
        "_get_current_user",
        Mock(return_value=lab_admin_staff.user),
    )

    assert (
        lab_routes._get_current_staff_id()
        == lab_admin_staff.id
    )


def test_current_staff_rejects_user_without_staff(
    lab_routes,
    user,
    monkeypatch,
):
    from app.core.exceptions import DomainError

    monkeypatch.setattr(
        lab_routes,
        "_get_current_user",
        Mock(return_value=user),
    )
    monkeypatch.setattr(
        lab_routes.db.session,
        "execute",
        Mock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(first=lambda: None)
            )
        ),
    )

    with pytest.raises(
        DomainError,
        match="not associated with a staff record",
    ):
        lab_routes._get_current_staff()


def test_serialize_lab_test(lab_routes):
    obj = test_obj()

    result = lab_routes._serialize_lab_test(obj)

    assert result["id"] == 1
    assert result["name"] == "CBC"
    assert result["sample_type"] == SampleType.BLOOD.value
    assert result["price"] == "25.00"
    assert result["critical_low"] == "2.000"
    assert result["critical_high"] == "40.000"


def test_serialize_lab_order_item(lab_routes):
    result = lab_routes._serialize_lab_order_item(
        item_obj()
    )

    assert result["id"] == 1
    assert result["test"]["name"] == "CBC"
    assert result["result_value"] == "10"
    assert result["flag"] == LabResultFlag.NORMAL.value


def test_serialize_lab_order(lab_routes):
    result = lab_routes._serialize_lab_order(
        order_obj()
    )

    assert result["id"] == 1
    assert result["status"] == LabOrderStatus.IN_PROGRESS.value
    assert result["ordered_by_id"] == 1
    assert result["collected_by_id"] == 2
    assert result["processed_by_id"] == 3
    assert len(result["items"]) == 1


# ============================================================================
# AUTH
# ============================================================================


def test_endpoints_require_auth(client):
    response = client.get("/api/lab/tests")

    assert response.status_code in (401, 422)


@pytest.mark.parametrize(
    "header_fixture,path",
    [
        ("lab_doctor_headers", "/api/lab/tests"),
        ("lab_receptionist_headers", "/api/lab/tests"),
        ("lab_technician_headers", "/api/lab/tests"),
    ],
)
def test_view_roles_can_list_tests(
    client,
    request,
    header_fixture,
    path,
):
    headers = request.getfixturevalue(header_fixture)

    response = client.get(
        path,
        headers=headers,
    )

    # The request should reach the route/service layer rather than fail
    # at role authorization.
    assert response.status_code != 403


# ============================================================================
# LAB TEST CATALOG
# ============================================================================


def test_create_lab_test_success(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=test_obj())

    monkeypatch.setattr(
        lab_routes,
        "create_lab_test",
        service,
    )

    response = client.post(
        "/api/lab/tests",
        headers=lab_admin_headers,
        json={
            "name": "CBC",
            "loinc_code": "12345-6",
            "code": "CBC",
            "sample_type": "blood",
            "reference_range": "5 - 20",
            "unit": "mg/dL",
            "price": "25.00",
            "critical_low": "2.000",
            "critical_high": "40.000",
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.get_json()["success"] is True
    assert service.call_args.kwargs["name"] == "CBC"


def test_create_lab_test_uses_authenticated_clinic(
    client,
    lab_admin_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=test_obj())

    monkeypatch.setattr(
        lab_routes,
        "create_lab_test",
        service,
    )

    response = client.post(
        "/api/lab/tests",
        headers=lab_admin_headers,
        json={
            "name": "CBC",
            "clinic_id": 9999,
        },
    )

    assert response.status_code == 400
    service.assert_not_called()


def test_create_lab_test_rejects_unknown_fields(
    client,
    lab_admin_headers,
):
    response = client.post(
        "/api/lab/tests",
        headers=lab_admin_headers,
        json={
            "name": "CBC",
            "unexpected": "value",
        },
    )

    assert response.status_code == 422


def test_create_lab_test_is_admin_only(
    client,
    lab_doctor_headers,
):
    response = client.post(
        "/api/lab/tests",
        headers=lab_doctor_headers,
        json={
            "name": "CBC",
        },
    )

    assert response.status_code == 403


def test_list_lab_tests_success(
    client,
    lab_admin_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(
        return_value=[test_obj(clinic_id=None), test_obj(id=2)]
    )

    monkeypatch.setattr(
        lab_routes,
        "list_lab_tests",
        service,
    )

    response = client.get(
        "/api/lab/tests",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 2
    assert service.call_args.kwargs["clinic_id"] == lab_admin_staff.clinic_id


def test_list_lab_tests_forwards_active_only(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=[])

    monkeypatch.setattr(
        lab_routes,
        "list_lab_tests",
        service,
    )

    response = client.get(
        "/api/lab/tests?active_only=false",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["active_only"] is False


def test_list_lab_tests_rejects_unknown_query_parameter(
    client,
    lab_admin_headers,
):
    response = client.get(
        "/api/lab/tests?unknown=value",
        headers=lab_admin_headers,
    )

    assert response.status_code == 422


def test_get_lab_test_success(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "get_lab_test",
        Mock(return_value=test_obj()),
    )

    response = client.get(
        "/api/lab/tests/1",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "CBC"


def test_get_lab_test_forwards_authenticated_clinic(
    client,
    lab_admin_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=test_obj())

    monkeypatch.setattr(
        lab_routes,
        "get_lab_test",
        service,
    )

    response = client.get(
        "/api/lab/tests/1",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["clinic_id"] == lab_admin_staff.clinic_id


def test_get_lab_test_maps_domain_error(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    from app.core.exceptions import NotFoundError

    monkeypatch.setattr(
        lab_routes,
        "get_lab_test",
        Mock(side_effect=NotFoundError("missing")),
    )

    response = client.get(
        "/api/lab/tests/999",
        headers=lab_admin_headers,
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "missing"


def test_update_lab_test_success(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    service = Mock(
        return_value=test_obj(name="Updated CBC")
    )

    monkeypatch.setattr(
        lab_routes,
        "update_lab_test",
        service,
    )

    response = client.patch(
        "/api/lab/tests/1",
        headers=lab_admin_headers,
        json={
            "name": "Updated CBC",
        },
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["name"] == "Updated CBC"


def test_update_lab_test_is_admin_only(
    client,
    lab_doctor_headers,
):
    response = client.patch(
        "/api/lab/tests/1",
        headers=lab_doctor_headers,
        json={
            "name": "Updated",
        },
    )

    assert response.status_code == 403


def test_update_lab_test_forwards_partial_fields(
    client,
    lab_admin_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=test_obj())

    monkeypatch.setattr(
        lab_routes,
        "update_lab_test",
        service,
    )

    response = client.patch(
        "/api/lab/tests/1",
        headers=lab_admin_headers,
        json={
            "critical_low": "3.000",
        },
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["clinic_id"] == lab_admin_staff.clinic_id
    assert service.call_args.kwargs["critical_low"] == Decimal("3.000")


# ============================================================================
# LAB ORDERS
# ============================================================================


def test_create_lab_order_success(
    client,
    lab_admin_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(return_value=order_obj())

    monkeypatch.setattr(
        lab_routes,
        "create_lab_order",
        service,
    )

    response = client.post(
        "/api/lab/orders",
        headers=lab_admin_headers,
        json={
            "patient_id": 10,
            "test_ids": [1, 2],
            "consultation_id": 5,
        },
    )

    assert response.status_code == 201
    assert service.call_args.kwargs["clinic_id"] == lab_admin_staff.clinic_id
    assert service.call_args.kwargs["ordered_by_id"] == lab_admin_staff.id


def test_create_lab_order_rejects_client_clinic_and_actor(
    client,
    lab_admin_headers,
):
    response = client.post(
        "/api/lab/orders",
        headers=lab_admin_headers,
        json={
            "patient_id": 10,
            "test_ids": [1],
            "clinic_id": 999,
            "ordered_by_id": 999,
        },
    )

    assert response.status_code == 422


def test_create_lab_order_requires_clinical_role(
    client,
    lab_receptionist_headers,
):
    response = client.post(
        "/api/lab/orders",
        headers=lab_receptionist_headers,
        json={
            "patient_id": 10,
            "test_ids": [1],
        },
    )

    assert response.status_code == 403


def test_get_lab_order_success(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "get_lab_order",
        Mock(return_value=order_obj()),
    )

    response = client.get(
        "/api/lab/orders/1",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["id"] == 1


def test_list_orders_for_patient_success(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "list_orders_for_patient",
        Mock(return_value=[order_obj()]),
    )

    response = client.get(
        "/api/lab/orders?patient_id=10",
        headers=lab_admin_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["data"][0]["patient_id"] == 10


def test_list_orders_for_patient_rejects_unknown_query(
    client,
    lab_admin_headers,
):
    response = client.get(
        "/api/lab/orders?patient_id=10&unknown=x",
        headers=lab_admin_headers,
    )

    assert response.status_code == 422


def test_list_orders_for_patient_requires_patient_id(
    client,
    lab_admin_headers,
):
    response = client.get(
        "/api/lab/orders",
        headers=lab_admin_headers,
    )

    assert response.status_code == 422


# ============================================================================
# SAMPLE COLLECTION
# ============================================================================


def test_collect_sample_success(
    client,
    lab_technician_headers,
    lab_admin_staff,
    monkeypatch,
    lab_routes,
):
    service = Mock(
        return_value=order_obj(
            status=LabOrderStatus.SAMPLE_COLLECTED,
            collected_by_id=lab_admin_staff.id,
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "collect_sample",
        service,
    )

    response = client.post(
        "/api/lab/orders/1/collect-sample",
        headers=lab_technician_headers,
        json={
            "scanned_qr_code": "LAB-123",
        },
    )

    assert response.status_code == 200
    assert (
        service.call_args.kwargs["collected_by_id"]
        == lab_routes._get_current_staff_id()
    )


def test_collect_sample_rejects_client_actor(
    client,
    lab_technician_headers,
):
    response = client.post(
        "/api/lab/orders/1/collect-sample",
        headers=lab_technician_headers,
        json={
            "scanned_qr_code": "LAB-123",
            "collected_by_id": 999,
        },
    )

    assert response.status_code == 422


def test_collect_sample_maps_service_error(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    from app.core.exceptions import ConflictError

    monkeypatch.setattr(
        lab_routes,
        "collect_sample",
        Mock(side_effect=ConflictError("QR mismatch")),
    )

    response = client.post(
        "/api/lab/orders/1/collect-sample",
        headers=lab_technician_headers,
        json={
            "scanned_qr_code": "BAD",
        },
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "QR mismatch"


# ============================================================================
# EQUIPMENT
# ============================================================================


def test_link_equipment_success(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    service = Mock(
        return_value=order_obj(
            status=LabOrderStatus.IN_PROGRESS,
            equipment_reference_id="EQ-100",
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "link_equipment",
        service,
    )

    response = client.post(
        "/api/lab/orders/1/equipment",
        headers=lab_technician_headers,
        json={
            "equipment_reference_id": "EQ-100",
        },
    )

    assert response.status_code == 200
    assert (
        service.call_args.kwargs["equipment_reference_id"]
        == "EQ-100"
    )


def test_link_equipment_rejects_empty_payload(
    client,
    lab_technician_headers,
):
    response = client.post(
        "/api/lab/orders/1/equipment",
        headers=lab_technician_headers,
        json={},
    )

    assert response.status_code == 422


# ============================================================================
# SAMPLE PROCESSING
# ============================================================================


def test_process_sample_success(
    client,
    lab_technician_headers,
    lab_technician_context,
    monkeypatch,
    lab_routes,
):
    staff, _ = lab_technician_context

    service = Mock(
        return_value=order_obj(
            status=LabOrderStatus.IN_PROGRESS,
            processed_by_id=staff.id,
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "process_sample",
        service,
    )

    response = client.post(
        "/api/lab/orders/1/process",
        headers=lab_technician_headers,
        json={
            "equipment_reference_id": "EQ-100",
        },
    )

    assert response.status_code == 200
    assert (
        service.call_args.kwargs["processed_by_id"]
        == staff.id
    )


def test_process_sample_rejects_client_actor(
    client,
    lab_technician_headers,
):
    response = client.post(
        "/api/lab/orders/1/process",
        headers=lab_technician_headers,
        json={
            "processed_by_id": 999,
        },
    )

    assert response.status_code == 422


# ============================================================================
# RESULT ENTRY
# ============================================================================


def test_enter_result_success(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    service = Mock(
        return_value=item_obj(
            result_value="10",
            flag=LabResultFlag.NORMAL,
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "enter_result",
        service,
    )

    response = client.post(
        "/api/lab/order-items/1/result",
        headers=lab_technician_headers,
        json={
            "result_value": "10",
            "flag": "critical",
            "result_notes": "Normal",
            "result_file_url": "report.pdf",
        },
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["result_value"] == "10"
    assert service.call_args.kwargs["flag"] == LabResultFlag.CRITICAL


def test_enter_result_rejects_unknown_field(
    client,
    lab_technician_headers,
):
    response = client.post(
        "/api/lab/order-items/1/result",
        headers=lab_technician_headers,
        json={
            "result_value": "10",
            "actor_id": 999,
        },
    )

    assert response.status_code == 422


def test_enter_result_maps_domain_error(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    from app.core.exceptions import ConflictError

    monkeypatch.setattr(
        lab_routes,
        "enter_result",
        Mock(
            side_effect=ConflictError(
                "Cannot modify after verification"
            )
        ),
    )

    response = client.post(
        "/api/lab/order-items/1/result",
        headers=lab_technician_headers,
        json={
            "result_value": "10",
        },
    )

    assert response.status_code == 409


# ============================================================================
# VERIFICATION
# ============================================================================


def test_verify_results_success(
    client,
    lab_technician_headers,
    lab_technician_context,
    monkeypatch,
    lab_routes,
):
    staff, _ = lab_technician_context

    service = Mock(
        return_value=order_obj(
            verified_by_id=staff.id,
            verified_at=datetime.now(timezone.utc),
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "verify_results",
        service,
    )

    response = client.post(
        "/api/lab/orders/1/verify",
        headers=lab_technician_headers,
        json={},
    )

    assert response.status_code == 200
    assert (
        service.call_args.kwargs["verified_by_id"]
        == staff.id
    )


def test_verify_results_rejects_client_actor(
    client,
    lab_technician_headers,
):
    response = client.post(
        "/api/lab/orders/1/verify",
        headers=lab_technician_headers,
        json={
            "verified_by_id": 999,
        },
    )

    assert response.status_code == 422


def test_verify_results_accepts_empty_body(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "verify_results",
        Mock(return_value=order_obj()),
    )

    response = client.post(
        "/api/lab/orders/1/verify",
        headers=lab_technician_headers,
        json={},
    )

    assert response.status_code == 200


# ============================================================================
# COMPLETION
# ============================================================================


def test_complete_order_success(
    client,
    lab_technician_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "complete_order",
        Mock(
            return_value=order_obj(
                status=LabOrderStatus.COMPLETED,
                verified_by_id=4,
                verified_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
        ),
    )

    response = client.post(
        "/api/lab/orders/1/complete",
        headers=lab_technician_headers,
    )

    assert response.status_code == 200
    assert (
        response.get_json()["data"]["status"]
        == LabOrderStatus.COMPLETED.value
    )


def test_complete_order_requires_technician_role(
    client,
    lab_doctor_headers,
):
    response = client.post(
        "/api/lab/orders/1/complete",
        headers=lab_doctor_headers,
    )

    assert response.status_code == 403


# ============================================================================
# CANCELLATION
# ============================================================================


def test_cancel_order_success(
    client,
    lab_doctor_headers,
    lab_doctor_context,
    monkeypatch,
    lab_routes,
):
    staff, _ = lab_doctor_context

    service = Mock(
        return_value=order_obj(
            status=LabOrderStatus.CANCELLED,
            cancellation_reason="Patient request",
        )
    )

    monkeypatch.setattr(
        lab_routes,
        "cancel_order",
        service,
    )

    response = client.post(
        "/api/lab/orders/1/cancel",
        headers=lab_doctor_headers,
        json={
            "reason": " Patient request ",
        },
    )

    assert response.status_code == 200
    assert service.call_args.kwargs["cancelled_by_id"] == staff.id
    assert service.call_args.kwargs["reason"] == " Patient request "


def test_cancel_order_rejects_client_actor(
    client,
    lab_doctor_headers,
):
    response = client.post(
        "/api/lab/orders/1/cancel",
        headers=lab_doctor_headers,
        json={
            "reason": "Cancel",
            "cancelled_by_id": 999,
        },
    )

    assert response.status_code == 422


def test_cancel_order_rejected_for_receptionist(
    client,
    lab_receptionist_headers,
):
    response = client.post(
        "/api/lab/orders/1/cancel",
        headers=lab_receptionist_headers,
        json={
            "reason": "Cancel",
        },
    )

    assert response.status_code == 403


# ============================================================================
# ERROR TRANSLATION
# ============================================================================


@pytest.mark.parametrize(
    "service_name,exc_class,status",
    [
        ("get_lab_order", "NotFoundError", 404),
        ("get_lab_order", "ConflictError", 409),
        ("get_lab_order", "ValidationError", 400),
    ],
)
def test_service_errors_are_mapped(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
    service_name,
    exc_class,
    status,
):
    from app.core.exceptions import (
        ConflictError,
        NotFoundError,
        ValidationError,
    )

    classes = {
        "NotFoundError": NotFoundError,
        "ConflictError": ConflictError,
        "ValidationError": ValidationError,
    }

    monkeypatch.setattr(
        lab_routes,
        service_name,
        Mock(side_effect=classes[exc_class]("boom")),
    )

    response = client.get(
        "/api/lab/orders/1",
        headers=lab_admin_headers,
    )

    assert response.status_code == status
    assert response.get_json()["error"] == "boom"


def test_unexpected_error_is_not_exposed(
    client,
    lab_admin_headers,
    monkeypatch,
    lab_routes,
):
    monkeypatch.setattr(
        lab_routes,
        "get_lab_order",
        Mock(side_effect=RuntimeError("SECRET INTERNAL DETAIL")),
    )

    response = client.get(
        "/api/lab/orders/1",
        headers=lab_admin_headers,
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "An unexpected error occurred"
    assert "SECRET INTERNAL DETAIL" not in response.text
