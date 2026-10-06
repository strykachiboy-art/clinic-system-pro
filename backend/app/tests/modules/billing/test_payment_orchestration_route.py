from datetime import datetime, timezone

from app.core.enums.billing_enums import (
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.modules.billing.models.billing_model import Payment
from app.modules.billing.services import payment_orchestration_service


def _admin_headers(
    app,
    make_user,
    auth_headers_for,
    clinic,
):
    from app.core.enums.role_enums import Role

    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    return auth_headers_for(
        user,
        clinic_context_id=clinic.id,
    )


def _payment_response(
    status=PaymentStatus.PENDING,
    failure_reason=None,
):
    now = datetime.now(timezone.utc)

    return Payment(
        id=1,
        invoice_id=1,
        amount="50.00",
        method=PaymentMethod.CARD,
        status=status,
        gateway=PaymentGateway.PAYSTACK,
        reference="PAY-1",
        gateway_transaction_id="123",
        failure_reason=failure_reason,
        created_at=now,
        updated_at=now,
        paid_at=(
            now
            if status == PaymentStatus.SUCCESSFUL
            else None
        ),
    )


def _payload():
    return {
        "invoice_id": 1,
        "amount": "50.00",
        "method": "card",
        "gateway": "paystack",
        "currency": "NGN",
    }


def test_payment_orchestration_requires_idempotency_key(
    client,
    app,
    auth_headers_for,
    make_user,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/v1/billing/payments/initialize",
        json=_payload(),
        headers=headers,
    )

    assert response.status_code == 400
    assert "Idempotency-Key is required" in (
        response.get_json()["error"]
    )


def test_payment_orchestration_pending_returns_202(
    client,
    app,
    auth_headers_for,
    make_user,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )
    payment = _payment_response()

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.orchestrate_payment",
        lambda **kwargs: {
            "payment": payment,
            "outcome": "pending",
        },
    )

    response = client.post(
        "/api/v1/billing/payments/initialize",
        json=_payload(),
        headers={
            **headers,
            "Idempotency-Key": "route-pending-1",
        },
    )

    assert response.status_code == 202

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["outcome"] == "pending"
    assert (
        body["data"]["payment"]["status"]
        == "pending"
    )


def test_payment_orchestration_failed_returns_422(
    client,
    app,
    auth_headers_for,
    make_user,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )
    payment = _payment_response(
        status=PaymentStatus.FAILED,
        failure_reason="Provider rejected",
    )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.orchestrate_payment",
        lambda **kwargs: {
            "payment": payment,
            "outcome": "failed",
        },
    )

    response = client.post(
        "/api/v1/billing/payments/initialize",
        json=_payload(),
        headers={
            **headers,
            "Idempotency-Key": "route-failed-1",
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["data"]["outcome"] == "failed"
    assert body["data"]["payment"]["status"] == "failed"


def test_payment_orchestration_success_returns_201(
    client,
    app,
    auth_headers_for,
    make_user,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )
    payment = _payment_response(
        status=PaymentStatus.SUCCESSFUL,
    )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.orchestrate_payment",
        lambda **kwargs: {
            "payment": payment,
            "outcome": "successful",
        },
    )

    response = client.post(
        "/api/v1/billing/payments/initialize",
        json=_payload(),
        headers={
            **headers,
            "Idempotency-Key": "route-success-1",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["outcome"] == "successful"
    assert (
        body["data"]["payment"]["status"]
        == "successful"
    )