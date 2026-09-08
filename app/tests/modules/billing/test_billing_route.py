import pytest

from decimal import Decimal
from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
    Payment,
)


def _admin_headers(
    app,
    make_user,
    auth_headers_for,
    clinic,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    return auth_headers_for(user)


def _invoice_response(
    invoice_id=1,
    clinic_id=1,
    patient_id=10,
    appointment_id=None,
    invoice_number="INV-1-20260907-ABC12345",
    total_amount="100.00",
    amount_paid="0.00",
    status=InvoiceStatus.ISSUED,
    due_date=None,
    is_insurance_claim=False,
    insurance_provider=None,
):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    return Invoice(
        id=invoice_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        invoice_number=invoice_number,
        total_amount=total_amount,
        amount_paid=amount_paid,
        status=status,
        due_date=due_date,
        is_insurance_claim=is_insurance_claim,
        insurance_provider=insurance_provider,
        created_at=now,
        updated_at=now,
    )


def _payment_response(
    payment_id=1,
    invoice_id=1,
    amount="50.00",
    method=PaymentMethod.CASH,
    status=PaymentStatus.SUCCESSFUL,
    gateway=None,
    reference=None,
    gateway_transaction_id=None,
    failure_reason=None,
    paid_at=None,
):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    return Payment(
        id=payment_id,
        invoice_id=invoice_id,
        amount=amount,
        method=method,
        status=status,
        gateway=gateway,
        reference=reference,
        gateway_transaction_id=gateway_transaction_id,
        failure_reason=failure_reason,
        created_at=now,
        updated_at=now,
        paid_at=paid_at or now,
    )


# ---------------------------------------------------------------------------
# Authentication / authorization
# ---------------------------------------------------------------------------


def test_billing_endpoints_require_authentication(
    client,
):
    endpoints = [
        ("post", "/api/billing/invoices", {
            "patient_id": 1,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        }),
        ("get", "/api/billing/invoices/outstanding", None),
        ("post", "/api/billing/payments", {
            "invoice_id": 1,
            "amount": "50.00",
            "method": "cash",
        }),
        ("post", "/api/billing/invoices/mark-overdue", None),
    ]

    for method, path, payload in endpoints:
        response = getattr(client, method)(
            path,
            json=payload,
        )

        assert response.status_code in (401, 422)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "post",
            "/api/billing/invoices",
            {
                "patient_id": 20,
                "items": [
                    {
                        "description": "Consultation",
                        "quantity": 1,
                        "unit_price": "100.00",
                    }
                ],
            },
        ),
        (
            "get",
            "/api/billing/invoices/outstanding",
            None,
        ),
        (
            "post",
            "/api/billing/payments",
            {
                "invoice_id": 100,
                "amount": "50.00",
                "method": "cash",
            },
        ),
        (
            "post",
            "/api/billing/invoices/mark-overdue",
            None,
        ),
    ],
)
def test_billing_endpoints_reject_non_admin(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    method,
    path,
    payload,
):
    user = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
    )

    headers = auth_headers_for(user)

    response = getattr(client, method)(
        path,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 403


def test_authenticated_user_without_clinic_is_rejected(
    app,
    client,
    make_user,
    auth_headers_for,
):
    user = make_user(
        role=Role.ADMIN,
    )

    headers = auth_headers_for(user)

    response = client.get(
        "/api/billing/invoices/outstanding",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "clinic" in body["error"].lower()


# ---------------------------------------------------------------------------
# Create invoice
# ---------------------------------------------------------------------------


def test_create_invoice_success(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    invoice = _invoice_response(
        invoice_id=1,
        clinic_id=clinic.id,
        patient_id=20,
        appointment_id=30,
        total_amount="200.00",
        amount_paid="0.00",
        status=InvoiceStatus.ISSUED,
        is_insurance_claim=True,
        insurance_provider="Test Insurance",
    )

    captured = {}

    def fake_create_invoice(**kwargs):
        captured.update(kwargs)
        return invoice

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.create_invoice",
        fake_create_invoice,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
            "appointment_id": 30,
            "due_date": "2026-09-30",
            "is_insurance_claim": True,
            "insurance_provider": "Test Insurance",
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 2,
                    "unit_price": "100.00",
                }
            ],
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["patient_id"] == 20
    assert body["data"]["appointment_id"] == 30
    assert body["data"]["total_amount"] == "200.00"
    assert body["data"]["amount_paid"] == "0.00"
    assert body["data"]["status"] == "issued"
    assert body["data"]["is_insurance_claim"] is True
    assert body["data"]["insurance_provider"] == "Test Insurance"

    assert captured["clinic_id"] == clinic.id
    assert captured["patient_id"] == 20
    assert captured["appointment_id"] == 30
    assert captured["is_insurance_claim"] is True
    assert captured["insurance_provider"] == "Test Insurance"

    assert captured["items"] == [
        {
            "description": "Consultation",
            "quantity": 2,
            "unit_price": Decimal("100.00"),
        }
    ]


def test_create_invoice_uses_authenticated_clinic(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    invoice = _invoice_response(
        clinic_id=clinic.id,
        patient_id=20,
    )

    captured = {}

    def fake_create_invoice(**kwargs):
        captured.update(kwargs)
        return invoice

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.create_invoice",
        fake_create_invoice,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
            "clinic_id": 999999,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert captured["clinic_id"] == clinic.id


def test_create_invoice_rejects_invalid_payload(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": -1,
            "items": [],
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_rejects_missing_items(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_create_invoice_rejects_invalid_item_quantity(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 0,
                    "unit_price": "100.00",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_create_invoice_rejects_negative_unit_price(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": "-1.00",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_create_invoice_returns_domain_error(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    def fake_create_invoice(**kwargs):
        raise ValidationError(
            "Patient does not belong to clinic"
        )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.create_invoice",
        fake_create_invoice,
    )

    response = client.post(
        "/api/billing/invoices",
        headers=headers,
        json={
            "patient_id": 20,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                    "unit_price": "100.00",
                }
            ],
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Patient does not belong to clinic"
    )


# ---------------------------------------------------------------------------
# Outstanding invoices
# ---------------------------------------------------------------------------


def test_get_outstanding_invoices_success(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    invoices = [
        _invoice_response(
            invoice_id=1,
            clinic_id=clinic.id,
            patient_id=10,
            invoice_number="INV-001",
            total_amount="100.00",
            amount_paid="0.00",
            status=InvoiceStatus.ISSUED,
        ),
        _invoice_response(
            invoice_id=2,
            clinic_id=clinic.id,
            patient_id=11,
            invoice_number="INV-002",
            total_amount="200.00",
            amount_paid="50.00",
            status=InvoiceStatus.PARTIALLY_PAID,
        ),
    ]

    captured = {}

    def fake_get_outstanding_invoices(**kwargs):
        captured.update(kwargs)
        return invoices

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.get_outstanding_invoices",
        fake_get_outstanding_invoices,
    )

    response = client.get(
        "/api/billing/invoices/outstanding",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["data"][0]["invoice_number"] == "INV-001"
    assert body["data"][1]["invoice_number"] == "INV-002"

    assert captured["clinic_id"] == clinic.id


def test_get_outstanding_invoices_returns_empty_list(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.get_outstanding_invoices",
        lambda **kwargs: [],
    )

    response = client.get(
        "/api/billing/invoices/outstanding",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"] == []


def test_get_outstanding_invoices_returns_domain_error(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    def fake_get_outstanding_invoices(**kwargs):
        raise ValidationError(
            "Invalid clinic"
        )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.get_outstanding_invoices",
        fake_get_outstanding_invoices,
    )

    response = client.get(
        "/api/billing/invoices/outstanding",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid clinic"


# ---------------------------------------------------------------------------
# Record payment
# ---------------------------------------------------------------------------


def test_record_payment_success(
    app,
    client,
    make_user,
    auth_headers_for,
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
        payment_id=1,
        invoice_id=100,
        amount="50.00",
        method=PaymentMethod.CASH,
        status=PaymentStatus.SUCCESSFUL,
    )

    captured = {}

    def fake_record_payment(**kwargs):
        captured.update(kwargs)
        return payment

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.record_payment",
        fake_record_payment,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "50.00",
            "method": "cash",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 1
    assert body["data"]["invoice_id"] == 100
    assert body["data"]["amount"] == "50.00"
    assert body["data"]["method"] == "cash"
    assert body["data"]["status"] == "successful"

    assert captured["clinic_id"] == clinic.id
    assert captured["invoice_id"] == 100
    assert str(captured["amount"]) == "50.00"
    assert captured["method"] == PaymentMethod.CASH


def test_record_payment_with_gateway_success(
    app,
    client,
    make_user,
    auth_headers_for,
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
        payment_id=2,
        invoice_id=100,
        amount="75.00",
        method=PaymentMethod.CARD,
        status=PaymentStatus.SUCCESSFUL,
        gateway=PaymentGateway.PAYSTACK,
        reference="REF-001",
        gateway_transaction_id="TXN-001",
    )

    captured = {}

    def fake_record_payment(**kwargs):
        captured.update(kwargs)
        return payment

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.record_payment",
        fake_record_payment,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "75.00",
            "method": "card",
            "gateway": "paystack",
            "reference": "REF-001",
            "gateway_transaction_id": "TXN-001",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["gateway"] == "paystack"
    assert body["data"]["reference"] == "REF-001"
    assert body["data"]["gateway_transaction_id"] == "TXN-001"

    assert captured["clinic_id"] == clinic.id
    assert captured["gateway"] == PaymentGateway.PAYSTACK
    assert captured["gateway_transaction_id"] == "TXN-001"


def test_record_payment_uses_authenticated_clinic(
    app,
    client,
    make_user,
    auth_headers_for,
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
        invoice_id=100,
    )

    captured = {}

    def fake_record_payment(**kwargs):
        captured.update(kwargs)
        return payment

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.record_payment",
        fake_record_payment,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "50.00",
            "method": "cash",
            "clinic_id": 999999,
        },
    )

    assert response.status_code == 201
    assert captured["clinic_id"] == clinic.id


def test_record_payment_rejects_invalid_payload(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": -1,
            "amount": "50.00",
            "method": "cash",
        },
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False


def test_record_payment_rejects_negative_amount(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "-50.00",
            "method": "cash",
        },
    )

    assert response.status_code == 422


def test_record_payment_rejects_missing_required_fields(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={},
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_returns_domain_error(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    def fake_record_payment(**kwargs):
        raise ConflictError(
            "Invoice is already fully paid"
        )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.record_payment",
        fake_record_payment,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "50.00",
            "method": "cash",
        },
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Invoice is already fully paid"
    )


def test_record_payment_returns_not_found_error(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    def fake_record_payment(**kwargs):
        raise NotFoundError(
            "Invoice 100 not found"
        )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.record_payment",
        fake_record_payment,
    )

    response = client.post(
        "/api/billing/payments",
        headers=headers,
        json={
            "invoice_id": 100,
            "amount": "50.00",
            "method": "cash",
        },
    )

    assert response.status_code == 404

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invoice 100 not found"


# ---------------------------------------------------------------------------
# Mark overdue
# ---------------------------------------------------------------------------


def test_mark_overdue_invoices_success(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    captured = {}

    def fake_mark_overdue_invoices(**kwargs):
        captured.update(kwargs)
        return 3

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.mark_overdue_invoices",
        fake_mark_overdue_invoices,
    )

    response = client.post(
        "/api/billing/invoices/mark-overdue",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["updated_count"] == 3
    assert captured["clinic_id"] == clinic.id


def test_mark_overdue_invoices_returns_zero(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.mark_overdue_invoices",
        lambda **kwargs: 0,
    )

    response = client.post(
        "/api/billing/invoices/mark-overdue",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["updated_count"] == 0


def test_mark_overdue_invoices_returns_domain_error(
    app,
    client,
    make_user,
    auth_headers_for,
    clinic,
    monkeypatch,
):
    headers = _admin_headers(
        app,
        make_user,
        auth_headers_for,
        clinic,
    )

    def fake_mark_overdue_invoices(**kwargs):
        raise ValidationError(
            "Invalid clinic"
        )

    monkeypatch.setattr(
        "app.modules.billing.routes.billing_route.mark_overdue_invoices",
        fake_mark_overdue_invoices,
    )

    response = client.post(
        "/api/billing/invoices/mark-overdue",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Invalid clinic"