from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.enums.role_enums import Role
from app.modules.billing.models.billing_model import Invoice, InvoiceItem, Payment


BASE_URL = "/api/billing"


def invoice_payload(clinic, patient, **overrides):
    payload = {
        "clinic_id": clinic.id,
        "patient_id": patient.id,
        "due_date": (date.today() + timedelta(days=7)).isoformat(),
        "is_insurance_claim": False,
        "items": [
            {
                "description": "Consultation",
                "quantity": 1,
                "unit_price": "5000.00",
            }
        ],
    }
    payload.update(overrides)
    return payload


def payment_payload(invoice, **overrides):
    payload = {
        "invoice_id": invoice.id,
        "amount": "2000.00",
        "method": PaymentMethod.CASH.value,
    }
    payload.update(overrides)
    return payload


def create_invoice_directly(db, clinic, patient, **overrides):
    invoice = Invoice(
        clinic_id=clinic.id,
        patient_id=patient.id,
        invoice_number=overrides.pop(
            "invoice_number",
            f"TEST-{clinic.id}-{patient.id}-{id(overrides)}",
        ),
        total_amount=overrides.pop("total_amount", Decimal("10000.00")),
        amount_paid=overrides.pop("amount_paid", Decimal("0.00")),
        status=overrides.pop("status", InvoiceStatus.ISSUED),
        due_date=overrides.pop(
            "due_date",
            date.today() + timedelta(days=7),
        ),
        is_insurance_claim=overrides.pop(
            "is_insurance_claim",
            False,
        ),
        insurance_provider=overrides.pop(
            "insurance_provider",
            None,
        ),
        appointment_id=overrides.pop("appointment_id", None),
        **overrides,
    )

    db.session.add(invoice)
    db.session.commit()

    return invoice


# ============================================================================
# POST /api/billing/invoices
# ============================================================================


def test_create_invoice_route_success(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    response = client.post(
        f"{BASE_URL}/invoices",
        json=invoice_payload(clinic, patient),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert "data" in body

    data = body["data"]

    assert data["id"] is not None
    assert data["clinic_id"] == clinic.id
    assert data["patient_id"] == patient.id
    assert data["appointment_id"] is None

    assert data["invoice_number"].startswith(
        f"INV-{clinic.id}-"
    )

    assert data["total_amount"] == "5000.00"
    assert data["amount_paid"] == "0.00"
    assert data["status"] == InvoiceStatus.ISSUED.value

    assert data["due_date"] == (
        date.today() + timedelta(days=7)
    ).isoformat()

    assert data["is_insurance_claim"] is False
    assert data["insurance_provider"] is None

    assert len(data["items"]) == 1

    item = data["items"][0]

    assert item["description"] == "Consultation"
    assert item["quantity"] == 1
    assert item["unit_price"] == "5000.00"
    assert item["subtotal"] == "5000.00"


def test_create_invoice_route_allows_multiple_items(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        items=[
            {
                "description": "Consultation",
                "quantity": 2,
                "unit_price": "5000.00",
            },
            {
                "description": "Laboratory Test",
                "quantity": 3,
                "unit_price": "1500.00",
            },
        ],
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert data["total_amount"] == "14500.00"
    assert len(data["items"]) == 2

    assert data["items"][0]["subtotal"] == "10000.00"
    assert data["items"][1]["subtotal"] == "4500.00"


def test_create_invoice_route_allows_insurance_claim(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        is_insurance_claim=True,
        insurance_provider="Test Health Insurance",
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["is_insurance_claim"] is True
    assert body["data"]["insurance_provider"] == (
        "Test Health Insurance"
    )


def test_create_invoice_route_rejects_missing_clinic_id(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(clinic, patient)
    payload.pop("clinic_id")

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_rejects_missing_patient_id(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(clinic, patient)
    payload.pop("patient_id")

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_rejects_empty_items(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        items=[],
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_rejects_invalid_quantity(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        items=[
            {
                "description": "Consultation",
                "quantity": 0,
                "unit_price": "5000.00",
            }
        ],
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_rejects_blank_description(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        items=[
            {
                "description": "   ",
                "quantity": 1,
                "unit_price": "5000.00",
            }
        ],
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_rejects_insurance_claim_without_provider(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
):
    payload = invoice_payload(
        clinic,
        patient,
        is_insurance_claim=True,
        insurance_provider=None,
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_invoice_route_requires_admin(
    client,
    clinic,
    patient,
    make_user,
    auth_headers_for,
):
    non_admin = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"{BASE_URL}/invoices",
        json=invoice_payload(clinic, patient),
        headers=auth_headers_for(
            non_admin,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_create_invoice_route_requires_authentication(
    client,
    clinic,
    patient,
):
    response = client.post(
        f"{BASE_URL}/invoices",
        json=invoice_payload(clinic, patient),
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body


# ============================================================================
# POST /api/billing/payments
# ============================================================================


def test_record_payment_route_success(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="3000.00",
            method=PaymentMethod.CASH.value,
            reference="CASH-001",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert data["id"] is not None
    assert data["invoice_id"] == invoice.id
    assert data["amount"] == "3000.00"
    assert data["method"] == PaymentMethod.CASH.value
    assert data["status"] == PaymentStatus.SUCCESSFUL.value
    assert data["gateway"] is None
    assert data["reference"] == "CASH-001"
    assert data["gateway_transaction_id"] is None
    assert data["failure_reason"] is None
    assert data["paid_at"] is not None


def test_record_payment_route_updates_invoice_balance(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="4000.00",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    db.session.refresh(invoice)

    assert invoice.amount_paid == Decimal("4000.00")
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID


def test_record_payment_route_can_fully_pay_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("5000.00"),
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="5000.00",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    db.session.refresh(invoice)

    assert invoice.amount_paid == Decimal("5000.00")
    assert invoice.status == InvoiceStatus.PAID


def test_record_payment_route_supports_gateway_payment(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="5000.00",
            method=PaymentMethod.CARD.value,
            gateway=PaymentGateway.PAYSTACK.value,
            gateway_transaction_id="TX-12345",
            reference="PAY-12345",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 201, response.get_json()

    body = response.get_json()

    assert body["success"] is True

    data = body["data"]

    assert data["method"] == PaymentMethod.CARD.value
    assert data["gateway"] == PaymentGateway.PAYSTACK.value
    assert data["gateway_transaction_id"] == "TX-12345"
    assert data["reference"] == "PAY-12345"


def test_record_payment_route_rejects_missing_invoice_id(
    client,
    clinic,
    user,
    auth_headers_for,
):
    payload = {
        "amount": "1000.00",
        "method": PaymentMethod.CASH.value,
    }

    response = client.post(
        f"{BASE_URL}/payments",
        json=payload,
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_non_positive_amount(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="0",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_invalid_method(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            method="invalid_method",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_gateway_without_transaction_id(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="1000.00",
            method=PaymentMethod.CARD.value,
            gateway=PaymentGateway.PAYSTACK.value,
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_overpayment(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("5000.00"),
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="6000.00",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_gateway_for_cash(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="1000.00",
            method=PaymentMethod.CASH.value,
            gateway=PaymentGateway.PAYSTACK.value,
            gateway_transaction_id="TX-123",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_cancelled_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        status=InvoiceStatus.CANCELLED,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(invoice),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_rejects_already_paid_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("5000.00"),
        amount_paid=Decimal("5000.00"),
        status=InvoiceStatus.PAID,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(
            invoice,
            amount="1000.00",
        ),
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 409

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_record_payment_route_requires_admin(
    client,
    clinic,
    patient,
    make_user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    doctor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(invoice),
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_record_payment_route_requires_authentication(
    client,
    clinic,
    patient,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
    )

    response = client.post(
        f"{BASE_URL}/payments",
        json=payment_payload(invoice),
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body


# ============================================================================
# GET /api/billing/invoices/outstanding
# ============================================================================


def test_get_outstanding_invoices_route_success(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    outstanding_invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
        status=InvoiceStatus.ISSUED,
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert isinstance(body["data"], list)

    ids = [invoice["id"] for invoice in body["data"]]

    assert outstanding_invoice.id in ids


def test_get_outstanding_invoices_route_includes_partially_paid(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("3000.00"),
        status=InvoiceStatus.PARTIALLY_PAID,
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    body = response.get_json()

    ids = [item["id"] for item in body["data"]]

    assert invoice.id in ids


def test_get_outstanding_invoices_route_includes_overdue(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        status=InvoiceStatus.OVERDUE,
        due_date=date.today() - timedelta(days=1),
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    body = response.get_json()

    ids = [item["id"] for item in body["data"]]

    assert invoice.id in ids


def test_get_outstanding_invoices_route_excludes_paid_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("5000.00"),
        amount_paid=Decimal("5000.00"),
        status=InvoiceStatus.PAID,
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    body = response.get_json()

    ids = [item["id"] for item in body["data"]]

    assert invoice.id not in ids


def test_get_outstanding_invoices_route_excludes_cancelled_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        status=InvoiceStatus.CANCELLED,
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    body = response.get_json()

    ids = [item["id"] for item in body["data"]]

    assert invoice.id not in ids


def test_get_outstanding_invoices_route_requires_admin(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_get_outstanding_invoices_route_requires_authentication(
    client,
):
    response = client.get(
        f"{BASE_URL}/invoices/outstanding",
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body


# ============================================================================
# POST /api/billing/invoices/mark-overdue
# ============================================================================


def test_mark_overdue_invoices_route_success(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    overdue_invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        status=InvoiceStatus.ISSUED,
        due_date=date.today() - timedelta(days=1),
    )

    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200, response.get_json()

    body = response.get_json()

    assert body["success"] is True
    assert "data" in body
    assert "updated_count" in body["data"]
    assert body["data"]["updated_count"] >= 1

    db.session.refresh(overdue_invoice)

    assert overdue_invoice.status == InvoiceStatus.OVERDUE


def test_mark_overdue_invoices_route_marks_partially_paid_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("4000.00"),
        status=InvoiceStatus.PARTIALLY_PAID,
        due_date=date.today() - timedelta(days=2),
    )

    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200, response.get_json()

    db.session.refresh(invoice)

    assert invoice.status == InvoiceStatus.OVERDUE


def test_mark_overdue_invoices_route_does_not_mark_future_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        status=InvoiceStatus.ISSUED,
        due_date=date.today() + timedelta(days=5),
    )

    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    db.session.refresh(invoice)

    assert invoice.status == InvoiceStatus.ISSUED


def test_mark_overdue_invoices_route_does_not_mark_paid_invoice(
    client,
    clinic,
    patient,
    user,
    auth_headers_for,
    db,
):
    invoice = create_invoice_directly(
        db,
        clinic,
        patient,
        total_amount=Decimal("5000.00"),
        amount_paid=Decimal("5000.00"),
        status=InvoiceStatus.PAID,
        due_date=date.today() - timedelta(days=5),
    )

    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
        headers=auth_headers_for(user, role=Role.ADMIN),
    )

    assert response.status_code == 200

    db.session.refresh(invoice)

    assert invoice.status == InvoiceStatus.PAID


def test_mark_overdue_invoices_route_requires_admin(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    doctor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
        headers=auth_headers_for(
            doctor,
            role=Role.DOCTOR,
        ),
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["error"] == "Insufficient permissions"


def test_mark_overdue_invoices_route_requires_authentication(
    client,
):
    response = client.post(
        f"{BASE_URL}/invoices/mark-overdue",
    )

    assert response.status_code in (401, 422)

    body = response.get_json()

    assert "msg" in body