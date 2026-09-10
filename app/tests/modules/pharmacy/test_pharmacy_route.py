from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.enums.pharmacy_enums import (
    DispenseStatus,
    DrugCategory,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.pharmacy.routes import pharmacy_routes


# ============================================================================
# HELPERS
# ============================================================================


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


def _utcnow():
    return datetime.now(timezone.utc)


def _auth_headers(make_authenticated_staff, clinic, role):
    """
    make_authenticated_staff returns:

        (staff, headers)

    The pharmacy route tests use:

        (headers, staff)
    """
    staff, headers = make_authenticated_staff(
        clinic,
        role,
    )

    return headers, staff


def _json_headers(make_authenticated_staff, clinic, role):
    headers, staff = _auth_headers(
        make_authenticated_staff,
        clinic,
        role,
    )

    headers = dict(headers)
    headers["Content-Type"] = "application/json"

    return headers, staff


def _mock_drug(**overrides):
    now = _utcnow()

    defaults = {
        "id": 1,
        "clinic_id": 1,
        "name": "Test Drug",
        "generic_name": "Test Generic",
        "category": DrugCategory.OTHER,
        "rxnorm_code": None,
        "barcode": None,
        "manufacturer": "Test Manufacturer",
        "dosage_form": "tablet",
        "strength": "500mg",
        "unit_price": Decimal("100.00"),
        "is_controlled": False,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    defaults.update(overrides)

    return SimpleNamespace(**defaults)


def _mock_batch(**overrides):
    """
    Schema-compatible DrugBatchResponseSchema test double.
    """
    now = _utcnow()

    defaults = {
        "id": 1,
        "clinic_id": 1,
        "drug_id": 1,
        "supplier_id": None,
        "batch_number": "BATCH-001",
        "quantity_on_hand": 100,
        "reorder_level": 20,
        "expiry_date": date.today() + timedelta(days=90),
        "received_at": now,
        "created_at": now,
        "updated_at": now,
    }

    defaults.update(overrides)

    return SimpleNamespace(**defaults)


def _mock_dispense_record(**overrides):
    """
    Schema-compatible DispenseRecordResponseSchema test double.
    """
    now = _utcnow()

    defaults = {
        "id": 1,
        "prescription_id": 1,
        "dispensed_by_id": 1,
        "status": DispenseStatus.PENDING,
        "notes": None,
        "dispensed_at": now,
        "created_at": now,
        "updated_at": now,
        "items": [],
    }

    defaults.update(overrides)

    return SimpleNamespace(**defaults)


def _mock_stock_summary(**overrides):
    """
    Schema-compatible StockSummaryResponseSchema test double.
    """
    defaults = {
        "clinic_id": 1,
        "drug_id": 7,
        "drug_name": "Test Drug",
        "quantity_on_hand": 100,
        "batch_count": 2,
    }

    defaults.update(overrides)

    return defaults


def _mock_paginated(
    items,
    *,
    total=None,
    page=DEFAULT_PAGE,
    per_page=DEFAULT_PER_PAGE,
):
    """
    Service-compatible paginated collection response.
    """
    if total is None:
        total = len(items)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ============================================================================
# DRUG LIST
# ============================================================================


def test_list_drugs_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    drugs = [
        _mock_drug(
            id=1,
            clinic_id=clinic.id,
        ),
        _mock_drug(
            id=2,
            clinic_id=clinic.id,
            name="Second Drug",
        ),
    ]

    service = Mock(
        return_value=_mock_paginated(
            drugs,
            total=2,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_drugs",
        service,
    )

    response = client.get(
        "/pharmacy/drugs",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["items"]
    assert len(body["data"]["items"]) == 2
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50

    service.assert_called_once_with(
        clinic_id=clinic.id,
        include_inactive=False,
        page=1,
        per_page=50,
    )


def test_list_drugs_include_inactive_true(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_drug(
                    clinic_id=clinic.id,
                    is_active=False,
                )
            ],
            total=1,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_drugs",
        service,
    )

    response = client.get(
        "/pharmacy/drugs?include_inactive=true",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["total"] == 1

    service.assert_called_once_with(
        clinic_id=clinic.id,
        include_inactive=True,
        page=1,
        per_page=50,
    )


def test_list_drugs_forwards_pagination(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_drug(
                    id=7,
                    clinic_id=clinic.id,
                )
            ],
            total=15,
            page=2,
            per_page=5,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_drugs",
        service,
    )

    response = client.get(
        "/pharmacy/drugs?page=2&per_page=5",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 5
    assert body["data"]["total"] == 15

    service.assert_called_once_with(
        clinic_id=clinic.id,
        include_inactive=False,
        page=2,
        per_page=5,
    )


def test_list_drugs_default_excludes_inactive(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated([])
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_drugs",
        service,
    )

    response = client.get(
        "/pharmacy/drugs",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["include_inactive"]
        is False
    )

    assert (
        service.call_args.kwargs["page"]
        == DEFAULT_PAGE
    )

    assert (
        service.call_args.kwargs["per_page"]
        == DEFAULT_PER_PAGE
    )


@pytest.mark.parametrize(
    "query_string",
    [
        "page=0",
        "page=-1",
        "per_page=0",
        "per_page=-1",
        "per_page=501",
    ],
)
def test_list_drugs_rejects_invalid_pagination(
    client,
    clinic,
    make_authenticated_staff,
    query_string,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        f"/pharmacy/drugs?{query_string}",
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# GET DRUG
# ============================================================================


def test_get_drug_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    drug = _mock_drug(
        id=7,
        clinic_id=clinic.id,
    )

    service = Mock(return_value=drug)

    monkeypatch.setattr(
        pharmacy_routes,
        "get_drug",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 7

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
    )


def test_get_drug_forwards_authenticated_clinic(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_drug(
            id=7,
            clinic_id=staff.clinic_id,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_drug",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["clinic_id"]
        == staff.clinic_id
    )


# ============================================================================
# CREATE DRUG
# ============================================================================


def test_create_drug_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    drug = _mock_drug(
        id=10,
        clinic_id=clinic.id,
        name="Paracetamol",
    )

    service = Mock(return_value=drug)

    monkeypatch.setattr(
        pharmacy_routes,
        "create_drug",
        service,
    )

    response = client.post(
        "/pharmacy/drugs",
        headers=headers,
        json={
            "name": "Paracetamol",
            "generic_name": "Acetaminophen",
            "category": DrugCategory.OTHER.value,
            "unit_price": "150.00",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["name"] == "Paracetamol"

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["name"] == "Paracetamol"
    assert kwargs["generic_name"] == "Acetaminophen"
    assert kwargs["unit_price"] == Decimal("150.00")


def test_create_drug_rejects_client_clinic_id(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs",
        headers=headers,
        json={
            "name": "Paracetamol",
            "clinic_id": 999,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": None},
        {"name": "   "},
        {"name": "X" * 151},
        {"unit_price": -1},
        {
            "name": "Paracetamol",
            "category": "INVALID_CATEGORY",
        },
    ],
)
def test_create_drug_rejects_invalid_payload(
    client,
    clinic,
    make_authenticated_staff,
    payload,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


def test_create_drug_rejects_unknown_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs",
        headers=headers,
        json={
            "name": "Paracetamol",
            "unknown_field": "attack",
        },
    )

    assert response.status_code == 422


# ============================================================================
# UPDATE DRUG
# ============================================================================


def test_update_drug_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    drug = _mock_drug(
        id=7,
        clinic_id=clinic.id,
        name="Updated Drug",
    )

    service = Mock(return_value=drug)

    monkeypatch.setattr(
        pharmacy_routes,
        "update_drug",
        service,
    )

    response = client.patch(
        "/pharmacy/drugs/7",
        headers=headers,
        json={
            "name": "Updated Drug",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["name"] == "Updated Drug"

    kwargs = service.call_args.kwargs

    assert kwargs["drug_id"] == 7
    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["name"] == "Updated Drug"


def test_update_drug_rejects_client_clinic_id(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.patch(
        "/pharmacy/drugs/7",
        headers=headers,
        json={
            "name": "Updated",
            "clinic_id": 999,
        },
    )

    assert response.status_code == 422


def test_update_drug_rejects_unknown_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.patch(
        "/pharmacy/drugs/7",
        headers=headers,
        json={
            "name": "Updated",
            "unknown_field": "attack",
        },
    )

    assert response.status_code == 422


# ============================================================================
# DRUG ACTIVE STATUS
# ============================================================================


def test_activate_drug_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    drug = _mock_drug(
        id=7,
        clinic_id=clinic.id,
        is_active=True,
    )

    service = Mock(return_value=drug)

    monkeypatch.setattr(
        pharmacy_routes,
        "set_drug_active_status",
        service,
    )

    response = client.post(
        "/pharmacy/drugs/7/activate",
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
        is_active=True,
    )


def test_deactivate_drug_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.ADMIN,
    )

    drug = _mock_drug(
        id=7,
        clinic_id=clinic.id,
        is_active=False,
    )

    service = Mock(return_value=drug)

    monkeypatch.setattr(
        pharmacy_routes,
        "set_drug_active_status",
        service,
    )

    response = client.post(
        "/pharmacy/drugs/7/deactivate",
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
        is_active=False,
    )


def test_activate_drug_is_admin_only(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs/7/activate",
        headers=headers,
    )

    assert response.status_code == 403


def test_deactivate_drug_is_admin_only(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs/7/deactivate",
        headers=headers,
    )

    assert response.status_code == 403


# ============================================================================
# LIST BATCHES
# ============================================================================


def test_list_batches_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    batches = [
        _mock_batch(
            id=1,
            clinic_id=clinic.id,
            drug_id=7,
        ),
        _mock_batch(
            id=2,
            clinic_id=clinic.id,
            drug_id=7,
            batch_number="BATCH-002",
        ),
    ]

    service = Mock(
        return_value=_mock_paginated(
            batches,
            total=2,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_batches",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7/batches",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]["items"]) == 2
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
        include_expired=True,
        page=1,
        per_page=50,
    )


def test_list_batches_can_exclude_expired(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_batch(
                    id=7,
                    clinic_id=clinic.id,
                    drug_id=7,
                )
            ]
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_batches",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7/batches?include_expired=false",
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
        include_expired=False,
        page=1,
        per_page=50,
    )


def test_list_batches_forwards_pagination(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_batch(
                    id=7,
                    clinic_id=clinic.id,
                    drug_id=7,
                )
            ],
            total=12,
            page=2,
            per_page=5,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_batches",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7/batches?page=2&per_page=5",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 5
    assert body["data"]["total"] == 12

    service.assert_called_once_with(
        drug_id=7,
        clinic_id=clinic.id,
        include_expired=True,
        page=2,
        per_page=5,
    )


@pytest.mark.parametrize(
    "query_string",
    [
        "page=0",
        "page=-1",
        "per_page=0",
        "per_page=-1",
        "per_page=501",
    ],
)
def test_list_batches_rejects_invalid_pagination(
    client,
    clinic,
    make_authenticated_staff,
    query_string,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        f"/pharmacy/drugs/7/batches?{query_string}",
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# GET BATCH
# ============================================================================


def test_get_batch_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    batch = _mock_batch(
        id=12,
        clinic_id=clinic.id,
    )

    service = Mock(return_value=batch)

    monkeypatch.setattr(
        pharmacy_routes,
        "get_batch",
        service,
    )

    response = client.get(
        "/pharmacy/batches/12",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 12

    service.assert_called_once_with(
        batch_id=12,
        clinic_id=clinic.id,
    )


# ============================================================================
# EXPIRING BATCHES
# ============================================================================


def test_list_expiring_batches_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    batches = [
        _mock_batch(
            id=3,
            clinic_id=clinic.id,
            expiry_date=date.today() + timedelta(days=10),
        )
    ]

    service = Mock(
        return_value=_mock_paginated(
            batches,
            total=1,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_expiring_batches",
        service,
    )

    response = client.get(
        "/pharmacy/batches/expiring",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]["items"]) == 1
    assert body["data"]["total"] == 1
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50

    service.assert_called_once_with(
        clinic_id=clinic.id,
        days=30,
        page=1,
        per_page=50,
    )


def test_list_expiring_batches_forwards_days(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated([])
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_expiring_batches",
        service,
    )

    response = client.get(
        "/pharmacy/batches/expiring?days=14",
        headers=headers,
    )

    assert response.status_code == 200

    service.assert_called_once_with(
        clinic_id=clinic.id,
        days=14,
        page=1,
        per_page=50,
    )


def test_list_expiring_batches_forwards_pagination(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_batch(
                    id=3,
                    clinic_id=clinic.id,
                )
            ],
            total=9,
            page=2,
            per_page=4,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_expiring_batches",
        service,
    )

    response = client.get(
        "/pharmacy/batches/expiring?days=14&page=2&per_page=4",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 4
    assert body["data"]["total"] == 9

    service.assert_called_once_with(
        clinic_id=clinic.id,
        days=14,
        page=2,
        per_page=4,
    )


@pytest.mark.parametrize(
    "days",
    [
        "-1",
        "-10",
        "abc",
    ],
)
def test_list_expiring_batches_rejects_invalid_days(
    client,
    clinic,
    make_authenticated_staff,
    days,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        f"/pharmacy/batches/expiring?days={days}",
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query_string",
    [
        "page=0",
        "page=-1",
        "per_page=0",
        "per_page=-1",
        "per_page=501",
    ],
)
def test_list_expiring_batches_rejects_invalid_pagination(
    client,
    clinic,
    make_authenticated_staff,
    query_string,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        f"/pharmacy/batches/expiring?{query_string}",
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# CREATE BATCH
# ============================================================================


def test_create_batch_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    expiry = date.today() + timedelta(days=90)

    batch = _mock_batch(
        id=15,
        clinic_id=clinic.id,
        drug_id=7,
        batch_number="NEW-BATCH",
        quantity_on_hand=50,
        expiry_date=expiry,
    )

    service = Mock(return_value=batch)

    monkeypatch.setattr(
        pharmacy_routes,
        "add_batch",
        service,
    )

    response = client.post(
        "/pharmacy/batches",
        headers=headers,
        json={
            "drug_id": 7,
            "batch_number": "NEW-BATCH",
            "quantity_on_hand": 50,
            "expiry_date": expiry.isoformat(),
            "reorder_level": 10,
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 15

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["drug_id"] == 7
    assert kwargs["batch_number"] == "NEW-BATCH"
    assert kwargs["quantity_on_hand"] == 50
    assert kwargs["reorder_level"] == 10


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "drug_id": 0,
            "batch_number": "B",
            "quantity_on_hand": 1,
            "expiry_date": (
                date.today() + timedelta(days=90)
            ).isoformat(),
        },
        {
            "drug_id": -1,
            "batch_number": "B",
            "quantity_on_hand": 1,
            "expiry_date": (
                date.today() + timedelta(days=90)
            ).isoformat(),
        },
        {
            "drug_id": 1,
            "batch_number": "",
            "quantity_on_hand": 1,
            "expiry_date": (
                date.today() + timedelta(days=90)
            ).isoformat(),
        },
        {
            "drug_id": 1,
            "batch_number": "B",
            "quantity_on_hand": -1,
            "expiry_date": (
                date.today() + timedelta(days=90)
            ).isoformat(),
        },
        {
            "drug_id": 1,
            "batch_number": "B",
            "quantity_on_hand": 1,
            "expiry_date": date.today().isoformat(),
        },
        {
            "drug_id": 1,
            "batch_number": "B",
            "quantity_on_hand": 1,
            "expiry_date": (
                date.today() - timedelta(days=1)
            ).isoformat(),
        },
    ],
)
def test_create_batch_rejects_invalid_payload(
    client,
    clinic,
    make_authenticated_staff,
    payload,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/batches",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


def test_create_batch_rejects_client_clinic_id(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/batches",
        headers=headers,
        json={
            "clinic_id": 999,
            "drug_id": 1,
            "batch_number": "BATCH",
            "quantity_on_hand": 10,
            "expiry_date": (
                date.today() + timedelta(days=90)
            ).isoformat(),
        },
    )

    assert response.status_code == 422


# ============================================================================
# STOCK SUMMARY
# ============================================================================


def test_get_stock_summary_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    summary = _mock_stock_summary(
        clinic_id=clinic.id,
        drug_id=7,
        drug_name="Test Drug",
        quantity_on_hand=100,
        batch_count=2,
    )

    service = Mock(return_value=summary)

    monkeypatch.setattr(
        pharmacy_routes,
        "get_stock_summary",
        service,
    )

    response = client.get(
        "/pharmacy/drugs/7/stock-summary",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True

    assert body["data"] == {
        "clinic_id": clinic.id,
        "drug_id": 7,
        "drug_name": "Test Drug",
        "quantity_on_hand": 100,
        "batch_count": 2,
    }

    service.assert_called_once_with(
        clinic_id=clinic.id,
        drug_id=7,
    )


# ============================================================================
# CREATE DISPENSE RECORD
# ============================================================================


def test_create_dispense_record_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    record = _mock_dispense_record(
        id=20,
        prescription_id=10,
        dispensed_by_id=staff.id,
        status=DispenseStatus.DISPENSED,
    )

    service = Mock(return_value=record)

    monkeypatch.setattr(
        pharmacy_routes,
        "create_dispense_record",
        service,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json={
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
            "notes": "Dispensed successfully",
        },
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 20

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["prescription_id"] == 10
    assert kwargs["dispensed_by_id"] == staff.id
    assert kwargs["items"] == [
        {
            "prescription_item_id": 5,
            "batch_id": 7,
            "quantity": 2,
        }
    ]
    assert kwargs["notes"] == "Dispensed successfully"


def test_create_dispense_record_derives_actor_from_auth(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_dispense_record(
            prescription_id=10,
            dispensed_by_id=staff.id,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "create_dispense_record",
        service,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json={
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
        },
    )

    assert response.status_code == 201

    kwargs = service.call_args.kwargs

    assert kwargs["clinic_id"] == clinic.id
    assert kwargs["dispensed_by_id"] == staff.id


def test_create_dispense_record_rejects_client_clinic_id(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json={
            "clinic_id": 999,
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
        },
    )

    assert response.status_code == 422


def test_create_dispense_record_rejects_client_actor(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json={
            "dispensed_by_id": 999,
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "prescription_id": 0,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
        },
        {
            "prescription_id": 10,
            "items": [],
        },
        {
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 0,
                    "batch_id": 7,
                    "quantity": 2,
                }
            ],
        },
        {
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 0,
                    "quantity": 2,
                }
            ],
        },
        {
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 0,
                }
            ],
        },
    ],
)
def test_create_dispense_record_rejects_invalid_payload(
    client,
    clinic,
    make_authenticated_staff,
    payload,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


def test_create_dispense_record_rejects_unknown_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json={
            "prescription_id": 10,
            "items": [
                {
                    "prescription_item_id": 5,
                    "batch_id": 7,
                    "quantity": 2,
                    "secret_field": "attack",
                }
            ],
        },
    )

    assert response.status_code == 422


# ============================================================================
# GET DISPENSE RECORD
# ============================================================================


def test_get_dispense_record_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    record = _mock_dispense_record(
        id=15,
        prescription_id=10,
        dispensed_by_id=1,
    )

    service = Mock(return_value=record)

    monkeypatch.setattr(
        pharmacy_routes,
        "get_dispense_record",
        service,
    )

    response = client.get(
        "/pharmacy/dispense/15",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 15

    service.assert_called_once_with(
        dispense_record_id=15,
        clinic_id=clinic.id,
    )


def test_get_dispense_record_is_tenant_scoped(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_dispense_record(
            id=15,
            prescription_id=10,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_dispense_record",
        service,
    )

    response = client.get(
        "/pharmacy/dispense/15",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["clinic_id"]
        == staff.clinic_id
    )


# ============================================================================
# LIST DISPENSE RECORDS
# ============================================================================


def test_list_dispense_records_for_prescription_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    records = [
        _mock_dispense_record(
            id=1,
            prescription_id=10,
        ),
        _mock_dispense_record(
            id=2,
            prescription_id=10,
        ),
    ]

    service = Mock(
        return_value=_mock_paginated(
            records,
            total=2,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_dispense_records_for_prescription",
        service,
    )

    response = client.get(
        "/pharmacy/prescriptions/10/dispense-records",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]["items"]) == 2
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 1
    assert body["data"]["per_page"] == 50

    service.assert_called_once_with(
        prescription_id=10,
        clinic_id=clinic.id,
        page=1,
        per_page=50,
    )


def test_list_dispense_records_for_prescription_forwards_pagination(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_paginated(
            [
                _mock_dispense_record(
                    id=3,
                    prescription_id=10,
                )
            ],
            total=9,
            page=2,
            per_page=4,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_dispense_records_for_prescription",
        service,
    )

    response = client.get(
        "/pharmacy/prescriptions/10/dispense-records"
        "?page=2&per_page=4",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 4
    assert body["data"]["total"] == 9

    service.assert_called_once_with(
        prescription_id=10,
        clinic_id=clinic.id,
        page=2,
        per_page=4,
    )


@pytest.mark.parametrize(
    "query_string",
    [
        "page=0",
        "page=-1",
        "per_page=0",
        "per_page=-1",
        "per_page=501",
    ],
)
def test_list_dispense_records_rejects_invalid_pagination(
    client,
    clinic,
    make_authenticated_staff,
    query_string,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        "/pharmacy/prescriptions/10/dispense-records"
        f"?{query_string}",
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# CANCEL DISPENSE RECORD
# ============================================================================


def test_cancel_dispense_record_success(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    record = _mock_dispense_record(
        id=20,
        prescription_id=10,
        status=DispenseStatus.CANCELLED,
    )

    service = Mock(return_value=record)

    monkeypatch.setattr(
        pharmacy_routes,
        "cancel_dispense_record",
        service,
    )

    response = client.post(
        "/pharmacy/dispense/20/cancel",
        headers=headers,
        json={},
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == 20

    service.assert_called_once_with(
        dispense_record_id=20,
        clinic_id=clinic.id,
    )


def test_cancel_dispense_record_is_tenant_scoped(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    service = Mock(
        return_value=_mock_dispense_record(
            id=20,
            status=DispenseStatus.CANCELLED,
        )
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "cancel_dispense_record",
        service,
    )

    response = client.post(
        "/pharmacy/dispense/20/cancel",
        headers=headers,
        json={},
    )

    assert response.status_code == 200

    assert (
        service.call_args.kwargs["clinic_id"]
        == staff.clinic_id
    )


def test_cancel_dispense_record_rejects_unknown_fields(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense/20/cancel",
        headers=headers,
        json={
            "unknown_field": "attack",
        },
    )

    assert response.status_code == 422


# ============================================================================
# AUTHORIZATION
# ============================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/pharmacy/drugs"),
        ("get", "/pharmacy/drugs/1"),
        ("post", "/pharmacy/drugs"),
        ("patch", "/pharmacy/drugs/1"),
        ("post", "/pharmacy/drugs/1/activate"),
        ("post", "/pharmacy/drugs/1/deactivate"),
        ("get", "/pharmacy/drugs/1/batches"),
        ("get", "/pharmacy/batches/1"),
        ("post", "/pharmacy/batches"),
        ("get", "/pharmacy/batches/expiring"),
        ("get", "/pharmacy/drugs/1/stock-summary"),
        ("post", "/pharmacy/dispense"),
        ("get", "/pharmacy/dispense/1"),
        (
            "get",
            "/pharmacy/prescriptions/1/dispense-records",
        ),
        ("post", "/pharmacy/dispense/1/cancel"),
    ],
)
def test_pharmacy_endpoints_require_auth(
    client,
    method,
    path,
):
    response = getattr(client, method)(path)

    assert response.status_code in (401, 422)


@pytest.mark.parametrize(
    "path",
    [
        "/pharmacy/drugs",
        "/pharmacy/drugs/1",
        "/pharmacy/drugs/1/batches",
        "/pharmacy/batches/1",
        "/pharmacy/batches/expiring",
        "/pharmacy/drugs/1/stock-summary",
        "/pharmacy/dispense/1",
        "/pharmacy/prescriptions/1/dispense-records",
    ],
)
def test_pharmacist_can_read_pharmacy_resources(
    client,
    clinic,
    make_authenticated_staff,
    path,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.get(
        path,
        headers=headers,
    )

    assert response.status_code != 403


# ============================================================================
# INVALID AUTHENTICATION
# ============================================================================


def test_invalid_token_is_rejected(client):
    response = client.get(
        "/pharmacy/drugs",
        headers={
            "Authorization": "Bearer definitely-invalid-token",
        },
    )

    assert response.status_code in (401, 422)


# ============================================================================
# DOMAIN ERROR TRANSLATION
# ============================================================================


@pytest.mark.parametrize(
    "exception,status_code",
    [
        (NotFoundError("Drug not found"), 404),
        (ConflictError("Drug conflict"), 409),
        (ValidationError("Invalid drug"), 422),
    ],
)
def test_get_drug_maps_domain_errors(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
    exception,
    status_code,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_drug",
        Mock(side_effect=exception),
    )

    response = client.get(
        "/pharmacy/drugs/1",
        headers=headers,
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


@pytest.mark.parametrize(
    "exception,status_code",
    [
        (NotFoundError("Batch not found"), 404),
        (ConflictError("Batch conflict"), 409),
        (ValidationError("Invalid batch"), 422),
    ],
)
def test_get_batch_maps_domain_errors(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
    exception,
    status_code,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_batch",
        Mock(side_effect=exception),
    )

    response = client.get(
        "/pharmacy/batches/1",
        headers=headers,
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


@pytest.mark.parametrize(
    "exception,status_code",
    [
        (NotFoundError("Dispense record not found"), 404),
        (ConflictError("Dispense conflict"), 409),
        (ValidationError("Invalid dispense"), 422),
    ],
)
def test_get_dispense_record_maps_domain_errors(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
    exception,
    status_code,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_dispense_record",
        Mock(side_effect=exception),
    )

    response = client.get(
        "/pharmacy/dispense/1",
        headers=headers,
    )

    assert response.status_code == status_code

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == str(exception)


# ============================================================================
# UNEXPECTED ERROR HANDLING
# ============================================================================


def test_unexpected_exception_does_not_expose_secret(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_drug",
        Mock(
            side_effect=RuntimeError(
                "SECRET INTERNAL DETAIL"
            )
        ),
    )

    response = client.get(
        "/pharmacy/drugs/1",
        headers=headers,
    )

    assert response.status_code == 500

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Internal server error"

    assert "SECRET INTERNAL DETAIL" not in response.get_data(
        as_text=True
    )


# ============================================================================
# JSON BODY VALIDATION
# ============================================================================


def test_create_drug_rejects_non_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/drugs",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422


def test_update_drug_rejects_non_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.patch(
        "/pharmacy/drugs/1",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422


def test_create_batch_rejects_non_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/batches",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422


def test_create_dispense_rejects_non_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422


def test_cancel_dispense_rejects_non_object_json(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _json_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.post(
        "/pharmacy/dispense/1/cancel",
        headers=headers,
        json=[
            "not",
            "an",
            "object",
        ],
    )

    assert response.status_code == 422


# ============================================================================
# METHOD VALIDATION
# ============================================================================


def test_drug_endpoint_rejects_unsupported_method(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.delete(
        "/pharmacy/drugs/1",
        headers=headers,
    )

    assert response.status_code == 405


def test_batch_endpoint_rejects_unsupported_method(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.delete(
        "/pharmacy/batches/1",
        headers=headers,
    )

    assert response.status_code == 405


def test_dispense_endpoint_rejects_unsupported_method(
    client,
    clinic,
    make_authenticated_staff,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    response = client.delete(
        "/pharmacy/dispense/1",
        headers=headers,
    )

    assert response.status_code == 405


# ============================================================================
# RESPONSE SHAPE
# ============================================================================


def test_get_drug_response_has_expected_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_drug",
        Mock(
            return_value=_mock_drug(
                id=7,
                clinic_id=clinic.id,
            )
        ),
    )

    response = client.get(
        "/pharmacy/drugs/7",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert body["success"] is True


def test_list_drugs_response_has_paginated_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_drugs",
        Mock(
            return_value=_mock_paginated(
                [
                    _mock_drug(
                        id=7,
                        clinic_id=clinic.id,
                    )
                ],
                total=7,
                page=2,
                per_page=5,
            )
        ),
    )

    response = client.get(
        "/pharmacy/drugs?page=2&per_page=5",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert set(body["data"].keys()) == {
        "items",
        "total",
        "page",
        "per_page",
    }

    assert body["success"] is True
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 5
    assert body["data"]["total"] == 7


def test_get_batch_response_has_expected_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_batch",
        Mock(
            return_value=_mock_batch(
                id=12,
                clinic_id=clinic.id,
            )
        ),
    )

    response = client.get(
        "/pharmacy/batches/12",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert body["success"] is True


def test_list_batches_response_has_paginated_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_batches",
        Mock(
            return_value=_mock_paginated(
                [
                    _mock_batch(
                        id=12,
                        clinic_id=clinic.id,
                        drug_id=7,
                    )
                ],
                total=8,
                page=2,
                per_page=4,
            )
        ),
    )

    response = client.get(
        "/pharmacy/drugs/7/batches?page=2&per_page=4",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert set(body["data"].keys()) == {
        "items",
        "total",
        "page",
        "per_page",
    }

    assert body["success"] is True
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 4
    assert body["data"]["total"] == 8


def test_expiring_batches_response_has_paginated_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_expiring_batches",
        Mock(
            return_value=_mock_paginated(
                [
                    _mock_batch(
                        id=5,
                        clinic_id=clinic.id,
                    )
                ],
                total=3,
                page=1,
                per_page=2,
            )
        ),
    )

    response = client.get(
        "/pharmacy/batches/expiring?per_page=2",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert set(body["data"].keys()) == {
        "items",
        "total",
        "page",
        "per_page",
    }

    assert body["data"]["total"] == 3
    assert body["data"]["per_page"] == 2


def test_stock_summary_response_has_expected_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_stock_summary",
        Mock(
            return_value=_mock_stock_summary(
                clinic_id=clinic.id,
                drug_id=7,
                drug_name="Test Drug",
                quantity_on_hand=100,
                batch_count=2,
            )
        ),
    )

    response = client.get(
        "/pharmacy/drugs/7/stock-summary",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert set(body["data"].keys()) == {
        "clinic_id",
        "drug_id",
        "drug_name",
        "quantity_on_hand",
        "batch_count",
    }


def test_list_dispense_records_response_has_paginated_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, _ = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "list_dispense_records_for_prescription",
        Mock(
            return_value=_mock_paginated(
                [
                    _mock_dispense_record(
                        id=20,
                        prescription_id=10,
                    )
                ],
                total=6,
                page=2,
                per_page=3,
            )
        ),
    )

    response = client.get(
        "/pharmacy/prescriptions/10/dispense-records"
        "?page=2&per_page=3",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert set(body["data"].keys()) == {
        "items",
        "total",
        "page",
        "per_page",
    }

    assert body["success"] is True
    assert body["data"]["total"] == 6
    assert body["data"]["page"] == 2
    assert body["data"]["per_page"] == 3


def test_dispense_response_has_expected_shape(
    client,
    clinic,
    make_authenticated_staff,
    monkeypatch,
):
    headers, staff = _auth_headers(
        make_authenticated_staff,
        clinic,
        Role.PHARMACIST,
    )

    monkeypatch.setattr(
        pharmacy_routes,
        "get_dispense_record",
        Mock(
            return_value=_mock_dispense_record(
                id=20,
                prescription_id=10,
                dispensed_by_id=staff.id,
            )
        ),
    )

    response = client.get(
        "/pharmacy/dispense/20",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert set(body.keys()) == {
        "success",
        "data",
    }

    assert body["success"] is True