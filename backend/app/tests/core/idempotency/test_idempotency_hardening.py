from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.enums.billing_enums import PaymentMethod
from app.core.exceptions import ValidationError
from app.core.idempotency.models.idempotency_model import (
    IdempotencyRecord,
)
from app.core.idempotency.services.idempotency_service import (
    normalize_idempotency_key,
    normalize_operation_name,
    request_fingerprint,
    reserve_idempotency_operation,
)


def test_rollback_removes_unfinished_reservation(
    clinic,
    user,
    db_session,
):
    key = "gate3-hardening-rollback-001"

    reservation_boundary = db_session.begin_nested()

    record, is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={
            "patient_id": 101,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                }
            ],
        },
    )

    assert is_new is True
    assert record.id > 0

    reservation_boundary.rollback()

    count = db_session.query(
        IdempotencyRecord
    ).filter(
        IdempotencyRecord.clinic_id == clinic.id,
        IdempotencyRecord.user_id == user.id,
        IdempotencyRecord.operation
        == "billing.invoice.create",
        IdempotencyRecord.idempotency_key == key,
    ).count()

    assert count == 0

    replay, replay_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={
            "patient_id": 101,
            "items": [
                {
                    "description": "Consultation",
                    "quantity": 1,
                }
            ],
        },
    )

    assert replay_is_new is True
    assert replay.id > 0


def test_same_key_isolated_by_operation(
    clinic,
    user,
):
    key = "gate3-hardening-operation-001"

    first, first_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    second, second_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.payment.record",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    assert first_is_new is True
    assert second_is_new is True
    assert first.id != second.id
    assert first.operation != second.operation


def test_same_key_isolated_by_user(
    clinic,
    user,
    make_user,
):
    second_user = make_user(
        clinic=clinic,
    )

    key = "gate3-hardening-user-001"

    first, first_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    second, second_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=second_user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    assert first_is_new is True
    assert second_is_new is True
    assert first.id != second.id
    assert first.user_id != second.user_id


def test_same_key_isolated_by_clinic(
    clinic,
    user,
    make_clinic,
    make_user,
):
    second_clinic = make_clinic()
    second_user = make_user(
        clinic=second_clinic,
    )

    key = "gate3-hardening-clinic-001"

    first, first_is_new = reserve_idempotency_operation(
        clinic_id=clinic.id,
        user_id=user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    second, second_is_new = reserve_idempotency_operation(
        clinic_id=second_clinic.id,
        user_id=second_user.id,
        operation="billing.invoice.create",
        idempotency_key=key,
        request_payload={"value": 1},
    )

    assert first_is_new is True
    assert second_is_new is True
    assert first.id != second.id
    assert first.clinic_id != second.clinic_id


def test_request_fingerprint_is_canonical_for_supported_types():
    first_payload = {
        "amount": Decimal("10.00"),
        "method": PaymentMethod.CASH,
        "due_date": date(2026, 10, 6),
        "created_at": datetime(
            2026,
            10,
            6,
            7,
            30,
            tzinfo=timezone.utc,
        ),
        "nested": {
            "b": 2,
            "a": 1,
        },
    }

    second_payload = {
        "nested": {
            "a": 1,
            "b": 2,
        },
        "created_at": datetime(
            2026,
            10,
            6,
            7,
            30,
            tzinfo=timezone.utc,
        ),
        "due_date": date(2026, 10, 6),
        "method": PaymentMethod.CASH,
        "amount": Decimal("10.00"),
    }

    assert request_fingerprint(first_payload) == (
        request_fingerprint(second_payload)
    )


def test_normalize_idempotency_key_strips_and_rejects_blank():
    assert normalize_idempotency_key(
        "  gate3-key-001  "
    ) == "gate3-key-001"

    with pytest.raises(
        ValidationError,
        match="Idempotency-Key cannot be blank",
    ):
        normalize_idempotency_key("   ")


def test_normalize_idempotency_key_rejects_overlong_value():
    with pytest.raises(
        ValidationError,
        match="Idempotency-Key cannot exceed 255 characters",
    ):
        normalize_idempotency_key("x" * 256)


def test_normalize_operation_name_rejects_blank():
    with pytest.raises(
        ValidationError,
        match="Idempotency operation cannot be blank",
    ):
        normalize_operation_name("   ")


@pytest.mark.parametrize(
    "clinic_id,user_id,message",
    [
        (
            0,
            1,
            "Clinic ID must be a positive integer",
        ),
        (
            1,
            0,
            "User ID must be a positive integer",
        ),
        (
            True,
            1,
            "Clinic ID must be a positive integer",
        ),
    ],
)
def test_reservation_rejects_invalid_scope_ids(
    clinic_id,
    user_id,
    message,
):
    with pytest.raises(
        ValidationError,
        match=message,
    ):
        reserve_idempotency_operation(
            clinic_id=clinic_id,
            user_id=user_id,
            operation="billing.invoice.create",
            idempotency_key="gate3-hardening-invalid-001",
            request_payload={"value": 1},
        )
