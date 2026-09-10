from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.core.enums.audit_enums import AuditAction
from app.core.enums.prescription_enums import PrescriptionStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

import app.modules.pharmacy.services.pharmacy_service as service


# ============================================================================
# HELPERS / FIXTURES
# ============================================================================


@pytest.fixture()
def pharmacy_service(monkeypatch):
    monkeypatch.setattr(
        service,
        "create_audit_log",
        Mock(),
    )

    return service


@pytest.fixture()
def active_clinic(clinic):
    if hasattr(clinic, "is_active"):
        clinic.is_active = True

    return clinic


def _future_date(days=30):
    return date.today() + timedelta(days=days)


def _future_datetime(days=30):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _make_second_clinic(db, source_clinic):
    clinic_model = type(source_clinic)
    mapper = clinic_model.__mapper__

    excluded = {
        "id",
        "created_at",
        "updated_at",
    }

    values = {}

    for column in mapper.columns:
        if column.name in excluded:
            continue

        value = getattr(
            source_clinic,
            column.name,
            None,
        )

        if value is not None:
            values[column.name] = value

    if hasattr(clinic_model, "name"):
        values["name"] = (
            f"Other Pharmacy Clinic {source_clinic.id}"
        )

    if hasattr(clinic_model, "code"):
        source_code = getattr(
            source_clinic,
            "code",
            None,
        )

        if source_code:
            values["code"] = (
                f"{source_code}-PHARM-{source_clinic.id}"
            )

    if hasattr(clinic_model, "slug"):
        source_slug = getattr(
            source_clinic,
            "slug",
            None,
        )

        if source_slug:
            values["slug"] = (
                f"{source_slug}-pharmacy-{source_clinic.id}"
            )

    other_clinic = clinic_model(
        **values
    )

    db.session.add(
        other_clinic
    )

    db.session.flush()

    return other_clinic


# ============================================================================
# DRUG LOOKUP / CATALOG
# ============================================================================


def test_get_drug_returns_clinic_drug(
    pharmacy_service,
    make_drug,
    clinic,
):
    drug = make_drug(clinic)

    result = pharmacy_service.get_drug(
        drug.id,
        clinic.id,
    )

    assert result.id == drug.id
    assert result.clinic_id == clinic.id


def test_get_drug_allows_global_drug(
    pharmacy_service,
    make_drug,
    clinic,
):
    drug = make_drug(None)

    result = pharmacy_service.get_drug(
        drug.id,
        clinic.id,
    )

    assert result.id == drug.id
    assert result.clinic_id is None


def test_get_drug_rejects_drug_from_another_clinic(
    pharmacy_service,
    make_drug,
    clinic,
):
    drug = make_drug(clinic)

    other_clinic_id = clinic.id + 999

    with pytest.raises(
        NotFoundError,
        match=f"Drug {drug.id} not found",
    ):
        pharmacy_service.get_drug(
            drug.id,
            other_clinic_id,
        )


def test_get_drug_not_found(
    pharmacy_service,
    clinic,
):
    with pytest.raises(
        NotFoundError,
        match="Drug 999999 not found",
    ):
        pharmacy_service.get_drug(
            999999,
            clinic.id,
        )


def test_get_drug_rejects_invalid_drug_id(
    pharmacy_service,
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="positive integer",
    ):
        pharmacy_service.get_drug(
            0,
            clinic.id,
        )


def test_get_drug_rejects_invalid_clinic_id(
    pharmacy_service,
):
    with pytest.raises(
        ValidationError,
        match="positive integer",
    ):
        pharmacy_service.get_drug(
            1,
            0,
        )


def test_list_drugs_returns_global_and_clinic_drugs(
    pharmacy_service,
    make_drug,
    clinic,
):
    global_drug = make_drug(None)
    clinic_drug = make_drug(clinic)

    result = pharmacy_service.list_drugs(
        clinic.id,
    )

    assert set(
        drug.id
        for drug in result["items"]
    ) >= {
        global_drug.id,
        clinic_drug.id,
    }

    assert result["total"] >= 2
    assert result["page"] == 1
    assert result["per_page"] == 50


def test_list_drugs_excludes_inactive_by_default(
    pharmacy_service,
    make_drug,
    clinic,
):
    active_drug = make_drug(
        clinic,
        is_active=True,
    )

    inactive_drug = make_drug(
        clinic,
        is_active=False,
    )

    result = pharmacy_service.list_drugs(
        clinic.id,
    )

    ids = {
        drug.id
        for drug in result["items"]
    }

    assert active_drug.id in ids
    assert inactive_drug.id not in ids


def test_list_drugs_can_include_inactive(
    pharmacy_service,
    make_drug,
    clinic,
):
    inactive_drug = make_drug(
        clinic,
        is_active=False,
    )

    result = pharmacy_service.list_drugs(
        clinic.id,
        include_inactive=True,
    )

    ids = {
        drug.id
        for drug in result["items"]
    }

    assert inactive_drug.id in ids


def test_list_drugs_paginates(
    pharmacy_service,
    make_drug,
    clinic,
):
    drugs = [
        make_drug(
            clinic,
            name=f"Drug {index:03d}",
        )
        for index in range(1, 6)
    ]

    result = pharmacy_service.list_drugs(
        clinic.id,
        page=2,
        per_page=2,
    )

    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["total"] >= 5
    assert len(result["items"]) == 2

    returned_ids = {
        drug.id
        for drug in result["items"]
    }

    assert returned_ids.isdisjoint(
        {
            drugs[0].id,
            drugs[1].id,
        }
    )


def test_list_drugs_beyond_last_page_returns_empty(
    pharmacy_service,
    make_drug,
    clinic,
):
    make_drug(
        clinic,
        name="Only Drug",
    )

    result = pharmacy_service.list_drugs(
        clinic.id,
        page=999,
        per_page=50,
    )

    assert result["items"] == []
    assert result["page"] == 999
    assert result["per_page"] == 50
    assert result["total"] >= 1


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (1, 0),
        (1, -1),
        (1, 501),
    ],
)
def test_list_drugs_rejects_invalid_pagination(
    pharmacy_service,
    clinic,
    page,
    per_page,
):
    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.list_drugs(
            clinic.id,
            page=page,
            per_page=per_page,
        )


def test_list_drugs_rejects_invalid_include_inactive(
    pharmacy_service,
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="include_inactive",
    ):
        pharmacy_service.list_drugs(
            clinic.id,
            include_inactive="true",
        )


# ============================================================================
# DRUG CREATION
# ============================================================================


def test_create_drug_success(
    pharmacy_service,
    active_clinic,
):
    drug = pharmacy_service.create_drug(
        clinic_id=active_clinic.id,
        name="Amoxicillin",
        generic_name="Amoxicillin",
        unit_price=Decimal("25.50"),
    )

    assert drug.id is not None
    assert drug.clinic_id == active_clinic.id
    assert drug.name == "Amoxicillin"
    assert drug.generic_name == "Amoxicillin"
    assert drug.unit_price == Decimal("25.50")
    assert drug.is_active is True


def test_create_drug_strips_name(
    pharmacy_service,
    active_clinic,
):
    drug = pharmacy_service.create_drug(
        clinic_id=active_clinic.id,
        name="  Amoxicillin  ",
    )

    assert drug.name == "Amoxicillin"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        None,
    ],
)
def test_create_drug_requires_name(
    pharmacy_service,
    active_clinic,
    name,
):
    with pytest.raises(
        ValidationError,
        match="name",
    ):
        pharmacy_service.create_drug(
            clinic_id=active_clinic.id,
            name=name,
        )


def test_create_drug_rejects_negative_price(
    pharmacy_service,
    active_clinic,
):
    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.create_drug(
            clinic_id=active_clinic.id,
            name="Drug A",
            unit_price=Decimal("-1.00"),
        )


def test_create_drug_rejects_invalid_controlled_flag(
    pharmacy_service,
    active_clinic,
):
    with pytest.raises(
        ValidationError,
        match="is_controlled",
    ):
        pharmacy_service.create_drug(
            clinic_id=active_clinic.id,
            name="Drug A",
            is_controlled="yes",
        )


def test_create_drug_rejects_duplicate_barcode(
    pharmacy_service,
    active_clinic,
):
    pharmacy_service.create_drug(
        clinic_id=active_clinic.id,
        name="Drug A",
        barcode="BAR-001",
    )

    with pytest.raises(
        ConflictError,
        match="barcode",
    ):
        pharmacy_service.create_drug(
            clinic_id=active_clinic.id,
            name="Drug B",
            barcode="BAR-001",
        )


def test_create_drug_rejects_missing_clinic(
    pharmacy_service,
    db,
):
    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.create_drug(
            clinic_id=None,
            name="Drug A",
        )


# ============================================================================
# DRUG UPDATE
# ============================================================================


def test_update_drug_success(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
        name="Old Name",
    )

    result = pharmacy_service.update_drug(
        drug_id=drug.id,
        clinic_id=active_clinic.id,
        name="New Name",
        manufacturer="Acme Pharma",
        unit_price=Decimal("50.00"),
    )

    assert result.name == "New Name"
    assert result.manufacturer == "Acme Pharma"
    assert result.unit_price == Decimal("50.00")


def test_update_drug_rejects_global_drug(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(None)

    with pytest.raises(
        ValidationError,
        match="Global catalog drugs cannot be modified",
    ):
        pharmacy_service.update_drug(
            drug_id=drug.id,
            clinic_id=active_clinic.id,
            name="Changed",
        )


def test_update_drug_rejects_unknown_field(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(active_clinic)

    with pytest.raises(
        ValidationError,
    ) as exc_info:
        pharmacy_service.update_drug(
            drug_id=drug.id,
            clinic_id=active_clinic.id,
            completely_unknown_field="x",
        )

    message = str(
        exc_info.value
    ).lower()

    assert (
        "unknown" in message
        or "unsupported" in message
        or "field" in message
        or "not allowed" in message
    )


def test_update_drug_rejects_empty_updates(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="field",
    ):
        pharmacy_service.update_drug(
            drug_id=drug.id,
            clinic_id=active_clinic.id,
        )


def test_update_drug_rejects_duplicate_barcode(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    first = make_drug(
        active_clinic,
        barcode="BAR-100",
    )

    second = make_drug(
        active_clinic,
        barcode="BAR-200",
    )

    with pytest.raises(
        ConflictError,
        match="barcode",
    ):
        pharmacy_service.update_drug(
            drug_id=second.id,
            clinic_id=active_clinic.id,
            barcode=first.barcode,
        )


def test_update_drug_rejects_invalid_drug_id(
    pharmacy_service,
    active_clinic,
):
    with pytest.raises(
        ValidationError,
        match="positive integer",
    ):
        pharmacy_service.update_drug(
            drug_id=0,
            clinic_id=active_clinic.id,
            name="Changed",
        )


# ============================================================================
# DRUG ACTIVE STATUS
# ============================================================================


def test_set_drug_active_status_deactivates_drug(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
        is_active=True,
    )

    result = pharmacy_service.set_drug_active_status(
        drug_id=drug.id,
        clinic_id=active_clinic.id,
        is_active=False,
    )

    assert result.is_active is False


def test_set_drug_active_status_reactivates_drug(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
        is_active=False,
    )

    result = pharmacy_service.set_drug_active_status(
        drug_id=drug.id,
        clinic_id=active_clinic.id,
        is_active=True,
    )

    assert result.is_active is True


def test_set_drug_active_status_rejects_invalid_flag(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="is_active",
    ):
        pharmacy_service.set_drug_active_status(
            drug_id=drug.id,
            clinic_id=active_clinic.id,
            is_active=1,
        )


# ============================================================================
# BATCH LOOKUP / LISTING
# ============================================================================


def test_get_batch_success(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    result = pharmacy_service.get_batch(
        batch.id,
        active_clinic.id,
    )

    assert result.id == batch.id


def test_get_batch_rejects_other_clinic(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    other_clinic_id = active_clinic.id + 999

    with pytest.raises(
        NotFoundError,
        match=f"Drug batch {batch.id} not found",
    ):
        pharmacy_service.get_batch(
            batch.id,
            other_clinic_id,
        )


def test_get_batch_rejects_invalid_batch_id(
    pharmacy_service,
    active_clinic,
):
    with pytest.raises(
        ValidationError,
        match="positive integer",
    ):
        pharmacy_service.get_batch(
            0,
            active_clinic.id,
        )


def test_list_batches_returns_only_clinic_batches(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    first = make_drug_batch(
        active_clinic,
        drug,
    )

    second = make_drug_batch(
        active_clinic,
        drug,
    )

    result = pharmacy_service.list_batches(
        drug.id,
        active_clinic.id,
    )

    ids = {
        batch.id
        for batch in result["items"]
    }

    assert first.id in ids
    assert second.id in ids
    assert result["total"] >= 2
    assert result["page"] == 1
    assert result["per_page"] == 50


def test_list_batches_excludes_expired(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    valid_batch = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=_future_date(30),
    )

    expired_batch = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=date.today() - timedelta(days=1),
    )

    result = pharmacy_service.list_batches(
        drug.id,
        active_clinic.id,
        include_expired=False,
    )

    ids = {
        batch.id
        for batch in result["items"]
    }

    assert valid_batch.id in ids
    assert expired_batch.id not in ids


def test_list_batches_can_include_expired(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    expired_batch = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=date.today() - timedelta(days=1),
    )

    result = pharmacy_service.list_batches(
        drug.id,
        active_clinic.id,
        include_expired=True,
    )

    ids = {
        batch.id
        for batch in result["items"]
    }

    assert expired_batch.id in ids


def test_list_batches_paginates(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    for index in range(1, 6):
        make_drug_batch(
            active_clinic,
            drug,
            batch_number=f"BATCH-{index:03d}",
            expiry_date=_future_date(
                index
            ),
        )

    result = pharmacy_service.list_batches(
        drug.id,
        active_clinic.id,
        page=2,
        per_page=2,
    )

    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert len(result["items"]) == 2


def test_list_batches_beyond_last_page_returns_empty(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    make_drug_batch(
        active_clinic,
        drug,
    )

    result = pharmacy_service.list_batches(
        drug.id,
        active_clinic.id,
        page=100,
        per_page=50,
    )

    assert result["items"] == []
    assert result["page"] == 100
    assert result["total"] == 1


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (1, 0),
        (1, -1),
        (1, 501),
    ],
)
def test_list_batches_rejects_invalid_pagination(
    pharmacy_service,
    active_clinic,
    make_drug,
    page,
    per_page,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.list_batches(
            drug.id,
            active_clinic.id,
            page=page,
            per_page=per_page,
        )


# ============================================================================
# BATCH CREATION
# ============================================================================


def test_add_batch_success(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
        is_active=True,
    )

    batch = pharmacy_service.add_batch(
        clinic_id=active_clinic.id,
        drug_id=drug.id,
        batch_number="AMOX-001",
        quantity_on_hand=100,
        expiry_date=_future_date(90),
        reorder_level=20,
    )

    assert batch.id is not None
    assert batch.clinic_id == active_clinic.id
    assert batch.drug_id == drug.id
    assert batch.quantity_on_hand == 100
    assert batch.batch_number == "AMOX-001"


def test_add_batch_rejects_inactive_drug(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
        is_active=False,
    )

    with pytest.raises(
        ValidationError,
        match="inactive",
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-001",
            quantity_on_hand=10,
            expiry_date=_future_date(),
        )


def test_add_batch_rejects_expired_batch(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="expiry",
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-EXPIRED",
            quantity_on_hand=10,
            expiry_date=date.today(),
        )


def test_add_batch_rejects_datetime_as_expiry_date(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="valid date",
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-DATETIME",
            quantity_on_hand=10,
            expiry_date=_future_datetime(),
        )


def test_add_batch_rejects_negative_quantity(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-NEG",
            quantity_on_hand=-1,
            expiry_date=_future_date(),
        )


def test_add_batch_rejects_boolean_quantity(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
        match="integer",
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-BOOL",
            quantity_on_hand=True,
            expiry_date=_future_date(),
        )


def test_add_batch_rejects_negative_reorder_level(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="B-REORDER",
            quantity_on_hand=10,
            reorder_level=-1,
            expiry_date=_future_date(),
        )


def test_add_batch_rejects_duplicate_batch_number(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        active_clinic,
    )

    pharmacy_service.add_batch(
        clinic_id=active_clinic.id,
        drug_id=drug.id,
        batch_number="DUP-001",
        quantity_on_hand=100,
        expiry_date=_future_date(),
    )

    with pytest.raises(
        ConflictError,
    ) as exc_info:
        pharmacy_service.add_batch(
            clinic_id=active_clinic.id,
            drug_id=drug.id,
            batch_number="DUP-001",
            quantity_on_hand=50,
            expiry_date=_future_date(),
        )

    message = str(
        exc_info.value
    ).lower()

    assert (
        "batch" in message
        or "duplicate" in message
        or "already" in message
    )


def test_add_batch_allows_global_drug(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        None,
        is_active=True,
    )

    batch = pharmacy_service.add_batch(
        clinic_id=active_clinic.id,
        drug_id=drug.id,
        batch_number="GLOBAL-001",
        quantity_on_hand=100,
        expiry_date=_future_date(90),
    )

    assert batch.clinic_id == active_clinic.id
    assert batch.drug_id == drug.id


# ============================================================================
# EXPIRING BATCHES / STOCK SUMMARY
# ============================================================================


def test_list_expiring_batches_returns_batches_within_window(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    expiring = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=_future_date(10),
        quantity_on_hand=20,
    )

    far_future = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=_future_date(100),
        quantity_on_hand=20,
    )

    result = pharmacy_service.list_expiring_batches(
        active_clinic.id,
        days=30,
    )

    ids = {
        batch.id
        for batch in result["items"]
    }

    assert expiring.id in ids
    assert far_future.id not in ids
    assert result["page"] == 1
    assert result["per_page"] == 50
    assert result["total"] >= 1


def test_list_expiring_batches_excludes_zero_stock(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    empty_batch = make_drug_batch(
        active_clinic,
        drug,
        expiry_date=_future_date(10),
        quantity_on_hand=0,
    )

    result = pharmacy_service.list_expiring_batches(
        active_clinic.id,
        days=30,
    )

    ids = {
        batch.id
        for batch in result["items"]
    }

    assert empty_batch.id not in ids


def test_list_expiring_batches_rejects_negative_days(
    pharmacy_service,
    active_clinic,
):
    with pytest.raises(
        ValidationError,
        match="days",
    ):
        pharmacy_service.list_expiring_batches(
            active_clinic.id,
            days=-1,
        )


def test_list_expiring_batches_paginates(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    for index in range(1, 6):
        make_drug_batch(
            active_clinic,
            drug,
            batch_number=f"EXP-{index:03d}",
            expiry_date=_future_date(
                index
            ),
            quantity_on_hand=10,
        )

    result = pharmacy_service.list_expiring_batches(
        active_clinic.id,
        days=30,
        page=2,
        per_page=2,
    )

    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert len(result["items"]) == 2


def test_list_expiring_batches_beyond_last_page_returns_empty(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    make_drug_batch(
        active_clinic,
        drug,
        expiry_date=_future_date(5),
        quantity_on_hand=10,
    )

    result = pharmacy_service.list_expiring_batches(
        active_clinic.id,
        days=30,
        page=99,
        per_page=50,
    )

    assert result["items"] == []
    assert result["page"] == 99
    assert result["total"] == 1


def test_get_stock_summary_counts_nonexpired_stock(
    pharmacy_service,
    active_clinic,
    make_drug,
    make_drug_batch,
):
    drug = make_drug(
        active_clinic,
    )

    make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=40,
        expiry_date=_future_date(30),
    )

    make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=60,
        expiry_date=_future_date(60),
    )

    make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=500,
        expiry_date=date.today() - timedelta(days=1),
    )

    summary = pharmacy_service.get_stock_summary(
        active_clinic.id,
        drug.id,
    )

    assert summary["quantity_on_hand"] == 100
    assert summary["batch_count"] == 2


# ============================================================================
# PRESCRIPTION LOOKUP
# ============================================================================


def test_get_prescription_for_pharmacy_success(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.ADMIN,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    result = pharmacy_service.get_prescription_for_pharmacy(
        prescription.id,
        active_clinic.id,
    )

    assert result.id == prescription.id
    assert result.clinic_id == active_clinic.id


def test_get_prescription_rejects_other_clinic(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.ADMIN,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    with pytest.raises(
        NotFoundError,
        match=f"Prescription {prescription.id} not found",
    ):
        pharmacy_service.get_prescription_for_pharmacy(
            prescription.id,
            active_clinic.id + 999,
        )


# ============================================================================
# DISPENSING VALIDATION
# ============================================================================


def test_create_dispense_record_rejects_empty_items(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    with pytest.raises(
        ValidationError,
        match="item",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[],
        )


def test_create_dispense_record_rejects_duplicate_entries(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=20,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=50,
    )

    duplicate_entry = {
        "prescription_item_id": item.id,
        "batch_id": batch.id,
        "quantity": 5,
    }

    with pytest.raises(
        ValidationError,
        match="Duplicate batch",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                duplicate_entry,
                duplicate_entry.copy(),
            ],
        )


def test_create_dispense_record_rejects_quantity_above_prescription(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    with pytest.raises(
        ConflictError,
        match="quantity",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 11,
                }
            ],
        )


def test_create_dispense_record_rejects_insufficient_stock(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=20,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=5,
    )

    with pytest.raises(
        ConflictError,
        match="stock",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 10,
                }
            ],
        )


def test_create_dispense_record_rejects_expired_batch(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=50,
        expiry_date=date.today() - timedelta(days=1),
    )

    with pytest.raises(
        ValidationError,
        match="expired or expires today",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


def test_create_dispense_record_rejects_zero_quantity(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        ValidationError,
        match="positive integer",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 0,
                }
            ],
        )


# ============================================================================
# DISPENSING SUCCESS
# ============================================================================


def test_create_dispense_record_partially_dispenses(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=30,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 10,
            }
        ],
    )

    assert record.id is not None
    assert record.status.value == "partially_dispensed"
    assert batch.quantity_on_hand == 90
    assert record.dispensed_at is not None


def test_create_dispense_record_fully_dispenses(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=30,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 30,
            }
        ],
    )

    assert record.status.value == "dispensed"
    assert batch.quantity_on_hand == 70
    assert record.dispensed_at is not None


def test_create_dispense_record_can_use_multiple_batches(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=50,
    )

    first_batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=20,
    )

    second_batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=50,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": first_batch.id,
                "quantity": 20,
            },
            {
                "prescription_item_id": item.id,
                "batch_id": second_batch.id,
                "quantity": 30,
            },
        ],
    )

    assert record.status.value == "dispensed"
    assert first_batch.quantity_on_hand == 0
    assert second_batch.quantity_on_hand == 20


# ============================================================================
# DISPENSE LOOKUP / LISTING
# ============================================================================


def test_get_dispense_record_success(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    result = pharmacy_service.get_dispense_record(
        record.id,
        active_clinic.id,
    )

    assert result.id == record.id


def test_get_dispense_record_rejects_other_clinic(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    with pytest.raises(
        NotFoundError,
        match=f"Dispense record {record.id} not found",
    ):
        pharmacy_service.get_dispense_record(
            record.id,
            active_clinic.id + 999,
        )


def test_list_dispense_records_for_prescription(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    result = (
        pharmacy_service.list_dispense_records_for_prescription(
            prescription.id,
            active_clinic.id,
        )
    )

    assert isinstance(
        result,
        dict,
    )

    assert result["items"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["per_page"] == 50


def test_list_dispense_records_for_prescription_paginates(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=100,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=500,
    )

    for quantity in [5, 5, 5, 5, 5]:
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": quantity,
                }
            ],
        )

    result = (
        pharmacy_service.list_dispense_records_for_prescription(
            prescription.id,
            active_clinic.id,
            page=2,
            per_page=2,
        )
    )

    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert len(result["items"]) == 2


def test_list_dispense_records_beyond_last_page_returns_empty(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    result = (
        pharmacy_service.list_dispense_records_for_prescription(
            prescription.id,
            active_clinic.id,
            page=999,
            per_page=50,
        )
    )

    assert result["items"] == []
    assert result["page"] == 999
    assert result["total"] == 0


@pytest.mark.parametrize(
    "page,per_page",
    [
        (0, 50),
        (-1, 50),
        (1, 0),
        (1, -1),
        (1, 501),
    ],
)
def test_list_dispense_records_rejects_invalid_pagination(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    page,
    per_page,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    with pytest.raises(
        ValidationError,
    ):
        pharmacy_service.list_dispense_records_for_prescription(
            prescription.id,
            active_clinic.id,
            page=page,
            per_page=per_page,
        )


# ============================================================================
# CANCELLATION
# ============================================================================


def test_cancel_dispense_record_restores_stock(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=30,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 10,
            }
        ],
    )

    assert batch.quantity_on_hand == 90

    result = pharmacy_service.cancel_dispense_record(
        record.id,
        active_clinic.id,
    )

    assert result.status.value == "cancelled"
    assert result.dispensed_at is None
    assert batch.quantity_on_hand == 100


def test_cancel_dispense_record_cannot_cancel_fully_dispensed(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 10,
            }
        ],
    )

    assert record.status.value == "dispensed"

    with pytest.raises(
        ConflictError,
        match="dispensed",
    ):
        pharmacy_service.cancel_dispense_record(
            record.id,
            active_clinic.id,
        )


def test_cancel_dispense_record_cannot_cancel_twice(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=20,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    pharmacy_service.cancel_dispense_record(
        record.id,
        active_clinic.id,
    )

    with pytest.raises(
        ConflictError,
        match="cancel",
    ):
        pharmacy_service.cancel_dispense_record(
            record.id,
            active_clinic.id,
        )


def test_cancel_dispense_record_rejects_other_clinic(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
    db,
):
    other_clinic = _make_second_clinic(
        db,
        active_clinic,
    )

    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=20,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    with pytest.raises(
        NotFoundError,
        match=f"Dispense record {record.id} not found",
    ):
        pharmacy_service.cancel_dispense_record(
            record.id,
            other_clinic.id,
        )


# ============================================================================
# PRESCRIPTION STATUS / EXPIRY
# ============================================================================


def test_dispensing_rejects_inactive_prescription(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
        status=PrescriptionStatus.CANCELLED,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        ValidationError,
        match="active",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


def test_dispensing_rejects_expired_prescription(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
        expires_at=datetime.now(
            timezone.utc
        ) - timedelta(days=1),
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        ValidationError,
        match="expired",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


# ============================================================================
# STAFF VALIDATION
# ============================================================================


def test_dispensing_rejects_wrong_staff_role(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.DOCTOR,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        ValidationError,
        match="not authorized for pharmacy operations",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


def test_dispensing_rejects_inactive_staff(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    staff.status = StaffStatus.SUSPENDED

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        ValidationError,
        match="not active",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=active_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


def test_dispensing_rejects_staff_from_other_clinic(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
    db,
):
    other_clinic = _make_second_clinic(
        db,
        active_clinic,
    )

    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    with pytest.raises(
        NotFoundError,
        match=f"Prescription {prescription.id} not found",
    ):
        pharmacy_service.create_dispense_record(
            clinic_id=other_clinic.id,
            prescription_id=prescription.id,
            dispensed_by_id=staff.id,
            items=[
                {
                    "prescription_item_id": item.id,
                    "batch_id": batch.id,
                    "quantity": 5,
                }
            ],
        )


# ============================================================================
# GLOBAL DRUG RULES
# ============================================================================


def test_global_drug_can_have_clinic_batch(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        None,
        is_active=True,
    )

    batch = pharmacy_service.add_batch(
        clinic_id=active_clinic.id,
        drug_id=drug.id,
        batch_number="GLOBAL-001",
        quantity_on_hand=100,
        expiry_date=_future_date(90),
    )

    assert batch.clinic_id == active_clinic.id
    assert batch.drug_id == drug.id


def test_global_drug_cannot_be_updated_by_clinic(
    pharmacy_service,
    active_clinic,
    make_drug,
):
    drug = make_drug(
        None,
    )

    with pytest.raises(
        ValidationError,
        match="Global catalog drugs cannot be modified",
    ):
        pharmacy_service.update_drug(
            drug_id=drug.id,
            clinic_id=active_clinic.id,
            name="Attempted Change",
        )


def test_global_drug_is_visible_to_multiple_clinics(
    pharmacy_service,
    active_clinic,
    make_drug,
    db,
):
    other_clinic = _make_second_clinic(
        db,
        active_clinic,
    )

    drug = make_drug(
        None,
        is_active=True,
    )

    first_result = pharmacy_service.get_drug(
        drug.id,
        active_clinic.id,
    )

    second_result = pharmacy_service.get_drug(
        drug.id,
        other_clinic.id,
    )

    assert first_result.id == drug.id
    assert second_result.id == drug.id


# ============================================================================
# AUDIT
# ============================================================================


def test_create_drug_writes_audit_log(
    pharmacy_service,
    active_clinic,
    monkeypatch,
):
    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    drug = pharmacy_service.create_drug(
        clinic_id=active_clinic.id,
        name="Audit Drug",
    )

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "Drug"
    assert kwargs["entity_id"] == drug.id


def test_update_drug_writes_audit_log(
    pharmacy_service,
    active_clinic,
    make_drug,
    monkeypatch,
):
    drug = make_drug(
        active_clinic,
        name="Before",
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    pharmacy_service.update_drug(
        drug_id=drug.id,
        clinic_id=active_clinic.id,
        name="After",
    )

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.UPDATE
    assert kwargs["entity_type"] == "Drug"
    assert kwargs["entity_id"] == drug.id


def test_set_drug_active_status_writes_audit_log(
    pharmacy_service,
    active_clinic,
    make_drug,
    monkeypatch,
):
    drug = make_drug(
        active_clinic,
        is_active=True,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    pharmacy_service.set_drug_active_status(
        drug_id=drug.id,
        clinic_id=active_clinic.id,
        is_active=False,
    )

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.STATUS_CHANGE
    assert kwargs["entity_type"] == "Drug"
    assert kwargs["entity_id"] == drug.id


def test_create_dispense_record_writes_audit_log(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
    monkeypatch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=10,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.CREATE
    assert kwargs["entity_type"] == "DispenseRecord"
    assert kwargs["entity_id"] == record.id
    assert kwargs["user_id"] == staff.user.id


def test_cancel_dispense_record_writes_audit_log(
    pharmacy_service,
    active_clinic,
    patient,
    make_authenticated_staff,
    make_prescription,
    make_prescription_item,
    make_drug,
    make_drug_batch,
    monkeypatch,
):
    staff, _ = make_authenticated_staff(
        active_clinic,
        Role.PHARMACIST,
    )

    prescription = make_prescription(
        active_clinic,
        patient,
        staff,
    )

    drug = make_drug(
        active_clinic,
    )

    item = make_prescription_item(
        prescription,
        drug,
        quantity=20,
    )

    batch = make_drug_batch(
        active_clinic,
        drug,
        quantity_on_hand=100,
    )

    record = pharmacy_service.create_dispense_record(
        clinic_id=active_clinic.id,
        prescription_id=prescription.id,
        dispensed_by_id=staff.id,
        items=[
            {
                "prescription_item_id": item.id,
                "batch_id": batch.id,
                "quantity": 5,
            }
        ],
    )

    audit = Mock()

    monkeypatch.setattr(
        service,
        "create_audit_log",
        audit,
    )

    pharmacy_service.cancel_dispense_record(
        record.id,
        active_clinic.id,
    )

    audit.assert_called_once()

    kwargs = audit.call_args.kwargs

    assert kwargs["action"] == AuditAction.STATUS_CHANGE
    assert kwargs["entity_type"] == "DispenseRecord"
    assert kwargs["entity_id"] == record.id
    assert kwargs["details"]["new_status"] == "cancelled"