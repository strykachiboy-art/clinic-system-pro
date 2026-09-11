from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
    AssetOwnership,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetUpdateSchema,
)
from app.modules.asset_control.services.asset_service import (
    create_asset,
    dispose_asset,
    get_asset,
    list_assets,
    retire_asset,
    update_asset,
)


# =============================================================================
# TEST CONSTANTS
# =============================================================================


NON_ACTIVE_STAFF_STATUS = next(
    (
        status
        for status in StaffStatus
        if status != StaffStatus.ACTIVE
    ),
    None,
)


# =============================================================================
# HELPERS
# =============================================================================


def audit_logs_for_asset(
    db,
    asset_id: int,
    action: AuditAction | None = None,
) -> list[AuditLog]:
    query = AuditLog.query.filter_by(
        entity_type="Asset",
        entity_id=asset_id,
    )

    if action is not None:
        query = query.filter_by(
            action=action,
        )

    return query.order_by(
        AuditLog.id.asc(),
    ).all()


def create_schema(
    **overrides,
) -> AssetCreateSchema:
    payload = {
        "asset_tag": "AST-TEST-001",
        "name": "Test Asset",
        "category": AssetCategory.MEDICAL_EQUIPMENT,
        "condition": AssetCondition.GOOD,
        "ownership": AssetOwnership.CLINIC,
        "maintenance_status": MaintenanceStatus.NOT_REQUIRED,
    }

    payload.update(overrides)

    return AssetCreateSchema.model_validate(
        payload
    )


def update_schema(
    **overrides,
) -> AssetUpdateSchema:
    payload = {
        "name": "Updated Asset",
    }

    payload.update(overrides)

    return AssetUpdateSchema.model_validate(
        payload
    )


# =============================================================================
# CREATE
# =============================================================================


def test_create_asset_success(
    db,
    clinic,
    user,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    data = create_schema(
        asset_tag="AST-1001",
        name="Portable Ultrasound",
        description="Portable diagnostic ultrasound",
        location="Radiology",
        assigned_to_id=staff.id,
        serial_number="SN-1001",
        manufacturer="Acme Medical",
        model_number="US-500",
        purchase_date=date(2025, 1, 10),
        purchase_cost=Decimal("250000.00"),
        supplier="Medical Supplier Ltd",
        warranty_expiry=date(2027, 1, 10),
        maintenance_status=MaintenanceStatus.SCHEDULED,
        last_maintenance_date=date(2026, 1, 10),
        next_maintenance_date=date(2026, 7, 10),
        notes="Primary radiology unit",
    )

    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=data,
    )

    assert asset.id is not None
    assert asset.clinic_id == clinic.id
    assert asset.asset_tag == "AST-1001"
    assert asset.name == "Portable Ultrasound"
    assert asset.description == (
        "Portable diagnostic ultrasound"
    )
    assert asset.location == "Radiology"
    assert asset.assigned_to_id == staff.id
    assert asset.purchase_cost == Decimal("250000.00")
    assert asset.status == AssetStatus.ACTIVE
    assert asset.is_active is True

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.CREATE,
    )

    assert len(logs) == 1
    assert logs[0].user_id == user.id


def test_create_asset_accepts_dict(
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data={
            "asset_tag": "AST-DICT-001",
            "name": "Created From Dict",
            "category": AssetCategory.COMPUTER,
        },
    )

    assert asset.asset_tag == "AST-DICT-001"
    assert asset.name == "Created From Dict"
    assert asset.category == AssetCategory.COMPUTER
    assert asset.status == AssetStatus.ACTIVE
    assert asset.is_active is True


def test_create_asset_server_controls_status(
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-SERVER-CONTROLLED",
        ),
    )

    assert asset.status == AssetStatus.ACTIVE
    assert asset.is_active is True


def test_create_asset_normalizes_optional_text(
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-TEXT-001",
            description="  Description  ",
            location="  Storage Room  ",
            serial_number="  SERIAL-1  ",
            manufacturer="  Manufacturer  ",
            model_number="  MODEL-1  ",
            supplier="  Supplier  ",
            notes="  Notes  ",
        ),
    )

    assert asset.description == "Description"
    assert asset.location == "Storage Room"
    assert asset.serial_number == "SERIAL-1"
    assert asset.manufacturer == "Manufacturer"
    assert asset.model_number == "MODEL-1"
    assert asset.supplier == "Supplier"
    assert asset.notes == "Notes"


def test_create_asset_converts_blank_optional_text_to_none(
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-BLANK-001",
            description="   ",
            location="   ",
            serial_number="   ",
            manufacturer="   ",
            model_number="   ",
            supplier="   ",
            notes="   ",
        ),
    )

    assert asset.description is None
    assert asset.location is None
    assert asset.serial_number is None
    assert asset.manufacturer is None
    assert asset.model_number is None
    assert asset.supplier is None
    assert asset.notes is None


@pytest.mark.parametrize(
    "clinic_id",
    [0, -1, True, False, "1", None],
)
def test_create_asset_rejects_invalid_clinic_id(
    user,
    clinic_id,
):
    with pytest.raises(ValidationError):
        create_asset(
            clinic_id=clinic_id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag=(
                    f"AST-BAD-CLINIC-{str(clinic_id)}"
                ),
            ),
        )


def test_create_asset_rejects_missing_clinic(
    user,
):
    with pytest.raises(NotFoundError):
        create_asset(
            clinic_id=999999,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag="AST-MISSING-CLINIC",
            ),
        )


def test_create_asset_rejects_inactive_clinic(
    db,
    clinic,
    user,
):
    clinic.status = ClinicStatus.INACTIVE
    db.session.flush()

    with pytest.raises(ValidationError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag="AST-INACTIVE-CLINIC",
            ),
        )


@pytest.mark.parametrize(
    "actor_user_id",
    [0, -1, True, False, "1", None],
)
def test_create_asset_rejects_invalid_actor_id(
    clinic,
    actor_user_id,
):
    with pytest.raises(ValidationError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=actor_user_id,
            data=create_schema(
                asset_tag=(
                    f"AST-BAD-ACTOR-{str(actor_user_id)}"
                ),
            ),
        )


def test_create_asset_rejects_duplicate_asset_tag(
    clinic,
    user,
    asset,
):
    with pytest.raises(ConflictError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag=asset.asset_tag,
            ),
        )


def test_create_asset_allows_same_tag_in_different_clinic(
    clinic,
    make_clinic,
    user,
    make_user,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    other_user = make_user(
        clinic=other_clinic,
    )

    first = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-SAME-TAG",
        ),
    )

    second = create_asset(
        clinic_id=other_clinic.id,
        actor_user_id=other_user.id,
        data=create_schema(
            asset_tag="AST-SAME-TAG",
        ),
    )

    assert first.id != second.id
    assert first.clinic_id == clinic.id
    assert second.clinic_id == other_clinic.id
    assert first.asset_tag == second.asset_tag


def test_create_asset_accepts_active_staff(
    clinic,
    user,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-ACTIVE-STAFF",
            assigned_to_id=staff.id,
        ),
    )

    assert asset.assigned_to_id == staff.id


def test_create_asset_rejects_missing_staff(
    clinic,
    user,
):
    with pytest.raises(NotFoundError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag="AST-MISSING-STAFF",
                assigned_to_id=999999,
            ),
        )


def test_create_asset_rejects_cross_clinic_staff(
    clinic,
    make_clinic,
    user,
    make_staff,
):
    other_clinic = make_clinic(
        name="Other Staff Clinic",
    )

    staff = make_staff(
        clinic=other_clinic,
        status=StaffStatus.ACTIVE,
    )

    with pytest.raises(NotFoundError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag="AST-CROSS-STAFF",
                assigned_to_id=staff.id,
            ),
        )


@pytest.mark.skipif(
    NON_ACTIVE_STAFF_STATUS is None,
    reason="StaffStatus has no non-ACTIVE status",
)
def test_create_asset_rejects_non_active_staff(
    clinic,
    user,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=NON_ACTIVE_STAFF_STATUS,
    )

    with pytest.raises(ValidationError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=create_schema(
                asset_tag="AST-INACTIVE-STAFF",
                assigned_to_id=staff.id,
            ),
        )


def test_create_asset_rejects_warranty_before_purchase(
    clinic,
    user,
):
    with pytest.raises(PydanticValidationError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "asset_tag": "AST-BAD-WARRANTY",
                "name": "Bad Warranty",
                "category": AssetCategory.COMPUTER,
                "purchase_date": date(2026, 1, 1),
                "warranty_expiry": date(2025, 12, 1),
            },
        )


def test_create_asset_rejects_next_maintenance_before_last(
    clinic,
    user,
):
    with pytest.raises(PydanticValidationError):
        create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "asset_tag": "AST-BAD-MAINTENANCE",
                "name": "Bad Maintenance",
                "category": AssetCategory.COMPUTER,
                "last_maintenance_date": date(2026, 8, 1),
                "next_maintenance_date": date(2026, 7, 1),
            },
        )


def test_create_asset_audit_contains_expected_values(
    db,
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-AUDIT-001",
            category=AssetCategory.COMPUTER,
            condition=AssetCondition.EXCELLENT,
            ownership=AssetOwnership.LEASED,
        ),
    )

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.CREATE,
    )

    assert len(logs) == 1

    audit = logs[0]

    assert audit.user_id == user.id
    assert audit.new_value["clinic_id"] == clinic.id
    assert audit.new_value["asset_tag"] == (
        "AST-AUDIT-001"
    )
    assert audit.new_value["name"] == "Test Asset"
    assert audit.new_value["category"] == (
        AssetCategory.COMPUTER.value
    )
    assert audit.new_value["condition"] == (
        AssetCondition.EXCELLENT.value
    )
    assert audit.new_value["ownership"] == (
        AssetOwnership.LEASED.value
    )
    assert audit.new_value["status"] == (
        AssetStatus.ACTIVE.value
    )


# =============================================================================
# GET
# =============================================================================


def test_get_asset_success(
    clinic,
    asset,
):
    result = get_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
    )

    assert result.id == asset.id
    assert result.clinic_id == clinic.id


def test_get_asset_is_tenant_scoped(
    clinic,
    make_clinic,
    asset,
):
    other_clinic = make_clinic(
        name="Tenant Boundary Clinic",
    )

    with pytest.raises(NotFoundError):
        get_asset(
            asset_id=asset.id,
            clinic_id=other_clinic.id,
        )


def test_get_asset_missing_asset(
    clinic,
):
    with pytest.raises(NotFoundError):
        get_asset(
            asset_id=999999,
            clinic_id=clinic.id,
        )


@pytest.mark.parametrize(
    "asset_id",
    [0, -1, True, False, "1", None],
)
def test_get_asset_rejects_invalid_asset_id(
    clinic,
    asset_id,
):
    with pytest.raises(ValidationError):
        get_asset(
            asset_id=asset_id,
            clinic_id=clinic.id,
        )


@pytest.mark.parametrize(
    "clinic_id",
    [0, -1, True, False, "1", None],
)
def test_get_asset_rejects_invalid_clinic_id(
    asset,
    clinic_id,
):
    with pytest.raises(ValidationError):
        get_asset(
            asset_id=asset.id,
            clinic_id=clinic_id,
        )


# =============================================================================
# LIST
# =============================================================================


def test_list_assets_returns_current_clinic_assets(
    clinic,
    make_clinic,
    make_asset,
):
    other_clinic = make_clinic(
        name="List Other Clinic",
    )

    first = make_asset(
        clinic=clinic,
        asset_tag="AST-LIST-001",
    )

    second = make_asset(
        clinic=clinic,
        asset_tag="AST-LIST-002",
    )

    foreign = make_asset(
        clinic=other_clinic,
        asset_tag="AST-LIST-003",
    )

    result = list_assets(
        clinic_id=clinic.id,
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert first.id in ids
    assert second.id in ids
    assert foreign.id not in ids


@pytest.mark.parametrize(
    "search_value",
    [
        "AST-SEARCH-TAG",
        "Searchable Name",
        "SERIAL-SEARCH",
        "Acme Search",
        "MODEL-SEARCH",
        "Storage Room",
    ],
)
def test_list_assets_searches_supported_fields(
    clinic,
    make_asset,
    search_value,
):
    asset = make_asset(
        clinic=clinic,
        asset_tag="AST-SEARCH-TAG",
        name="Searchable Name",
        serial_number="SERIAL-SEARCH",
        manufacturer="Acme Search",
        model_number="MODEL-SEARCH",
        location="Storage Room",
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "search": search_value,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert asset.id in ids


def test_list_assets_filters_category(
    clinic,
    make_asset,
):
    medical = make_asset(
        clinic=clinic,
        asset_tag="AST-CAT-MEDICAL",
        category=AssetCategory.MEDICAL_EQUIPMENT,
    )

    computer = make_asset(
        clinic=clinic,
        asset_tag="AST-CAT-COMPUTER",
        category=AssetCategory.COMPUTER,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "category": AssetCategory.COMPUTER,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert computer.id in ids
    assert medical.id not in ids


def test_list_assets_filters_status(
    clinic,
    make_asset,
):
    active = make_asset(
        clinic=clinic,
        asset_tag="AST-STATUS-ACTIVE",
        status=AssetStatus.ACTIVE,
        is_active=True,
    )

    retired = make_asset(
        clinic=clinic,
        asset_tag="AST-STATUS-RETIRED",
        status=AssetStatus.RETIRED,
        is_active=False,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "status": AssetStatus.RETIRED,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert retired.id in ids
    assert active.id not in ids


def test_list_assets_filters_condition(
    clinic,
    make_asset,
):
    good = make_asset(
        clinic=clinic,
        asset_tag="AST-CONDITION-GOOD",
        condition=AssetCondition.GOOD,
    )

    damaged = make_asset(
        clinic=clinic,
        asset_tag="AST-CONDITION-DAMAGED",
        condition=AssetCondition.DAMAGED,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "condition": AssetCondition.DAMAGED,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert damaged.id in ids
    assert good.id not in ids


def test_list_assets_filters_ownership(
    clinic,
    make_asset,
):
    clinic_owned = make_asset(
        clinic=clinic,
        asset_tag="AST-OWNERSHIP-CLINIC",
        ownership=AssetOwnership.CLINIC,
    )

    leased = make_asset(
        clinic=clinic,
        asset_tag="AST-OWNERSHIP-LEASED",
        ownership=AssetOwnership.LEASED,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "ownership": AssetOwnership.LEASED,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert leased.id in ids
    assert clinic_owned.id not in ids


def test_list_assets_filters_maintenance_status(
    clinic,
    make_asset,
):
    scheduled = make_asset(
        clinic=clinic,
        asset_tag="AST-MAINT-SCHEDULED",
        maintenance_status=MaintenanceStatus.SCHEDULED,
    )

    completed = make_asset(
        clinic=clinic,
        asset_tag="AST-MAINT-COMPLETED",
        maintenance_status=MaintenanceStatus.COMPLETED,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "maintenance_status":
                MaintenanceStatus.SCHEDULED,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert scheduled.id in ids
    assert completed.id not in ids


def test_list_assets_filters_assigned_staff(
    clinic,
    make_asset,
    make_staff,
):
    first_staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    second_staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    first_asset = make_asset(
        clinic=clinic,
        asset_tag="AST-ASSIGNED-001",
        assigned_to_id=first_staff.id,
    )

    second_asset = make_asset(
        clinic=clinic,
        asset_tag="AST-ASSIGNED-002",
        assigned_to_id=second_staff.id,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "assigned_to_id": first_staff.id,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert first_asset.id in ids
    assert second_asset.id not in ids


def test_list_assets_filters_is_active(
    clinic,
    make_asset,
):
    active = make_asset(
        clinic=clinic,
        asset_tag="AST-FILTER-ACTIVE",
        is_active=True,
    )

    inactive = make_asset(
        clinic=clinic,
        asset_tag="AST-FILTER-INACTIVE",
        is_active=False,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "is_active": False,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert inactive.id in ids
    assert active.id not in ids


def test_list_assets_supports_combined_filters(
    clinic,
    make_asset,
):
    target = make_asset(
        clinic=clinic,
        asset_tag="AST-COMBINED-TARGET",
        category=AssetCategory.COMPUTER,
        condition=AssetCondition.GOOD,
        ownership=AssetOwnership.CLINIC,
        maintenance_status=MaintenanceStatus.SCHEDULED,
        is_active=True,
    )

    non_matching_category = make_asset(
        clinic=clinic,
        asset_tag="AST-COMBINED-OTHER-1",
        category=AssetCategory.FURNITURE,
        condition=AssetCondition.GOOD,
        ownership=AssetOwnership.CLINIC,
        maintenance_status=MaintenanceStatus.SCHEDULED,
        is_active=True,
    )

    non_matching_status = make_asset(
        clinic=clinic,
        asset_tag="AST-COMBINED-OTHER-2",
        category=AssetCategory.COMPUTER,
        condition=AssetCondition.GOOD,
        ownership=AssetOwnership.CLINIC,
        maintenance_status=MaintenanceStatus.SCHEDULED,
        is_active=False,
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "category": AssetCategory.COMPUTER,
            "condition": AssetCondition.GOOD,
            "ownership": AssetOwnership.CLINIC,
            "maintenance_status":
                MaintenanceStatus.SCHEDULED,
            "is_active": True,
        },
    )

    ids = {
        item.id
        for item in result["items"]
    }

    assert target.id in ids
    assert non_matching_category.id not in ids
    assert non_matching_status.id not in ids


def test_list_assets_default_pagination(
    clinic,
    make_asset,
):
    for index in range(3):
        make_asset(
            clinic=clinic,
            asset_tag=f"AST-DEFAULT-{index}",
        )

    result = list_assets(
        clinic_id=clinic.id,
    )

    assert result["page"] == 1
    assert result["per_page"] == 50
    assert result["total"] == 3
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_prev"] is False
    assert len(result["items"]) == 3


def test_list_assets_custom_pagination(
    clinic,
    make_asset,
):
    for index in range(5):
        make_asset(
            clinic=clinic,
            asset_tag=f"AST-CUSTOM-{index}",
        )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "page": 2,
            "per_page": 2,
        },
    )

    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert result["pages"] == 3
    assert result["has_next"] is True
    assert result["has_prev"] is True
    assert len(result["items"]) == 2


def test_list_assets_last_page(
    clinic,
    make_asset,
):
    for index in range(5):
        make_asset(
            clinic=clinic,
            asset_tag=f"AST-LAST-{index}",
        )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "page": 3,
            "per_page": 2,
        },
    )

    assert result["page"] == 3
    assert result["per_page"] == 2
    assert result["total"] == 5
    assert result["pages"] == 3
    assert result["has_next"] is False
    assert result["has_prev"] is True
    assert len(result["items"]) == 1


def test_list_assets_empty_page(
    clinic,
    make_asset,
):
    make_asset(
        clinic=clinic,
        asset_tag="AST-EMPTY",
    )

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "page": 5,
            "per_page": 2,
        },
    )

    assert result["page"] == 5
    assert result["total"] == 1
    assert result["items"] == []
    assert result["has_next"] is False
    assert result["has_prev"] is True


def test_list_assets_orders_newest_first(
    db,
    clinic,
    make_asset,
):
    older = make_asset(
        clinic=clinic,
        asset_tag="AST-ORDER-OLDER",
    )

    newer = make_asset(
        clinic=clinic,
        asset_tag="AST-ORDER-NEWER",
    )

    older.created_at = (
        older.created_at - timedelta(days=2)
    )

    newer.created_at = (
        newer.created_at + timedelta(days=1)
    )

    db.session.flush()

    result = list_assets(
        clinic_id=clinic.id,
        query={
            "per_page": 50,
        },
    )

    ids = [
        item.id
        for item in result["items"]
    ]

    assert ids.index(newer.id) < ids.index(older.id)


def test_list_assets_accepts_maximum_page_size(
    clinic,
):
    result = list_assets(
        clinic_id=clinic.id,
        query={
            "page": 1,
            "per_page": 500,
        },
    )

    assert result["per_page"] == 500


def test_list_assets_rejects_page_zero(
    clinic,
):
    with pytest.raises(PydanticValidationError):
        list_assets(
            clinic_id=clinic.id,
            query={
                "page": 0,
            },
        )


def test_list_assets_rejects_per_page_zero(
    clinic,
):
    with pytest.raises(PydanticValidationError):
        list_assets(
            clinic_id=clinic.id,
            query={
                "per_page": 0,
            },
        )


def test_list_assets_rejects_per_page_above_maximum(
    clinic,
):
    with pytest.raises(PydanticValidationError):
        list_assets(
            clinic_id=clinic.id,
            query={
                "per_page": 501,
            },
        )


@pytest.mark.parametrize(
    "clinic_id",
    [0, -1, True, False, "1", None],
)
def test_list_assets_rejects_invalid_clinic_id(
    clinic_id,
):
    with pytest.raises(ValidationError):
        list_assets(
            clinic_id=clinic_id,
        )


# =============================================================================
# UPDATE
# =============================================================================


def test_update_asset_success(
    db,
    clinic,
    user,
    asset,
):
    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            name="Updated Asset Name",
            description="Updated description",
            location="Updated Room",
            condition=AssetCondition.EXCELLENT,
            supplier="Updated Supplier",
        ),
    )

    assert updated.name == "Updated Asset Name"
    assert updated.description == (
        "Updated description"
    )
    assert updated.location == "Updated Room"
    assert updated.condition == AssetCondition.EXCELLENT
    assert updated.supplier == "Updated Supplier"

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.UPDATE,
    )

    assert len(logs) == 1
    assert logs[0].user_id == user.id


def test_update_asset_accepts_dict(
    clinic,
    user,
    asset,
):
    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data={
            "name": "Updated From Dict",
        },
    )

    assert updated.name == "Updated From Dict"


def test_update_asset_can_clear_nullable_text(
    clinic,
    user,
    asset,
):
    asset.description = "Existing description"

    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            description=None,
        ),
    )

    assert updated.description is None


def test_update_asset_can_clear_staff_assignment(
    clinic,
    user,
    asset,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    asset.assigned_to_id = staff.id

    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            assigned_to_id=None,
        ),
    )

    assert updated.assigned_to_id is None


def test_update_asset_normalizes_text(
    clinic,
    user,
    asset,
):
    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            description="  Updated description  ",
            location="  Updated location  ",
            manufacturer="  Updated manufacturer  ",
        ),
    )

    assert updated.description == (
        "Updated description"
    )
    assert updated.location == "Updated location"
    assert updated.manufacturer == (
        "Updated manufacturer"
    )


def test_update_asset_rejects_empty_update(
    clinic,
    user,
    asset,
):
    with pytest.raises(ValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=AssetUpdateSchema(),
        )


def test_update_asset_no_change_creates_no_audit(
    db,
    clinic,
    user,
    asset,
):
    initial_logs = audit_logs_for_asset(
        db,
        asset.id,
    )

    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            name=asset.name,
        ),
    )

    final_logs = audit_logs_for_asset(
        db,
        asset.id,
    )

    assert updated.id == asset.id
    assert len(final_logs) == len(initial_logs)


def test_update_asset_rejects_duplicate_tag(
    clinic,
    user,
    asset,
    make_asset,
):
    duplicate = make_asset(
        clinic=clinic,
        asset_tag="AST-DUPLICATE-UPDATE",
    )

    with pytest.raises(ConflictError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                asset_tag=duplicate.asset_tag,
            ),
        )


def test_update_asset_allows_current_tag(
    clinic,
    user,
    asset,
):
    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            asset_tag=asset.asset_tag,
        ),
    )

    assert updated.asset_tag == asset.asset_tag


def test_update_asset_validates_staff_assignment(
    clinic,
    user,
    asset,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            assigned_to_id=staff.id,
        ),
    )

    assert updated.assigned_to_id == staff.id


def test_update_asset_rejects_cross_clinic_staff(
    clinic,
    make_clinic,
    user,
    asset,
    make_staff,
):
    other_clinic = make_clinic(
        name="Update Staff Other Clinic",
    )

    staff = make_staff(
        clinic=other_clinic,
        status=StaffStatus.ACTIVE,
    )

    with pytest.raises(NotFoundError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                assigned_to_id=staff.id,
            ),
        )


@pytest.mark.skipif(
    NON_ACTIVE_STAFF_STATUS is None,
    reason="StaffStatus has no non-ACTIVE status",
)
def test_update_asset_rejects_non_active_staff(
    clinic,
    user,
    asset,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=NON_ACTIVE_STAFF_STATUS,
    )

    with pytest.raises(ValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                assigned_to_id=staff.id,
            ),
        )


def test_update_asset_rejects_missing_asset(
    clinic,
    user,
):
    with pytest.raises(NotFoundError):
        update_asset(
            asset_id=999999,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                name="Should Not Work",
            ),
        )


def test_update_asset_rejects_wrong_clinic(
    clinic,
    make_clinic,
    user,
    asset,
):
    other_clinic = make_clinic(
        name="Wrong Update Clinic",
    )

    with pytest.raises(NotFoundError):
        update_asset(
            asset_id=asset.id,
            clinic_id=other_clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                name="Should Not Work",
            ),
        )


def test_update_asset_rejects_inactive_clinic(
    db,
    clinic,
    user,
    asset,
):
    clinic.status = ClinicStatus.INACTIVE
    db.session.flush()

    with pytest.raises(ValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=update_schema(
                name="Should Not Work",
            ),
        )


@pytest.mark.parametrize(
    "actor_user_id",
    [0, -1, True, False, "1", None],
)
def test_update_asset_rejects_invalid_actor_id(
    clinic,
    asset,
    actor_user_id,
):
    with pytest.raises(ValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=actor_user_id,
            data=update_schema(
                name="Should Not Work",
            ),
        )


def test_update_asset_rejects_status_field(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "status": AssetStatus.RETIRED,
            },
        )


def test_update_asset_rejects_is_active_field(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "is_active": False,
            },
        )


def test_update_asset_rejects_retirement_date_field(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "retirement_date": date.today(),
            },
        )


def test_update_asset_rejects_disposal_date_field(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "disposal_date": date.today(),
            },
        )


def test_update_asset_rejects_warranty_before_purchase(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "purchase_date": date(2026, 6, 1),
                "warranty_expiry": date(2026, 5, 1),
            },
        )


def test_update_asset_rejects_next_maintenance_before_last(
    clinic,
    user,
    asset,
):
    with pytest.raises(PydanticValidationError):
        update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "last_maintenance_date": date(2026, 8, 1),
                "next_maintenance_date": date(2026, 7, 1),
            },
        )


def test_update_asset_audit_contains_old_and_new_values(
    db,
    clinic,
    user,
    asset,
):
    old_name = asset.name

    update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            name="Audit Updated Name",
        ),
    )

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.UPDATE,
    )

    assert len(logs) == 1

    audit = logs[0]

    assert audit.old_value["name"] == old_name
    assert audit.new_value["name"] == (
        "Audit Updated Name"
    )
    assert audit.user_id == user.id


# =============================================================================
# RETIRE
# =============================================================================


def test_retire_asset_success(
    db,
    clinic,
    user,
    asset,
):
    retirement_date = date(2026, 8, 1)

    retired = retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        retirement_date=retirement_date,
    )

    assert retired.status == AssetStatus.RETIRED
    assert retired.is_active is False
    assert retired.retirement_date == retirement_date

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.STATUS_CHANGE,
    )

    assert len(logs) == 1
    assert logs[0].user_id == user.id
    assert logs[0].new_value["status"] == (
        AssetStatus.RETIRED.value
    )


def test_retire_asset_defaults_to_today(
    clinic,
    user,
    asset,
):
    retired = retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    assert retired.retirement_date == date.today()


def test_retire_asset_rejects_already_retired(
    clinic,
    user,
    asset,
):
    asset.status = AssetStatus.RETIRED
    asset.is_active = False

    with pytest.raises(ConflictError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )


def test_retire_asset_rejects_disposed(
    clinic,
    user,
    asset,
):
    asset.status = AssetStatus.DISPOSED
    asset.is_active = False

    with pytest.raises(ConflictError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )


def test_retire_asset_rejects_before_purchase_date(
    clinic,
    user,
    asset,
):
    asset.purchase_date = date(2026, 5, 1)

    with pytest.raises(ValidationError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            retirement_date=date(2026, 4, 1),
        )


def test_retire_asset_rejects_wrong_clinic(
    clinic,
    make_clinic,
    user,
    asset,
):
    other_clinic = make_clinic(
        name="Wrong Retirement Clinic",
    )

    with pytest.raises(NotFoundError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=other_clinic.id,
            actor_user_id=user.id,
        )


def test_retire_asset_rejects_inactive_clinic(
    db,
    clinic,
    user,
    asset,
):
    clinic.status = ClinicStatus.INACTIVE
    db.session.flush()

    with pytest.raises(ValidationError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )


@pytest.mark.parametrize(
    "actor_user_id",
    [0, -1, True, False, "1", None],
)
def test_retire_asset_rejects_invalid_actor_id(
    clinic,
    asset,
    actor_user_id,
):
    with pytest.raises(ValidationError):
        retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=actor_user_id,
        )


# =============================================================================
# DISPOSE
# =============================================================================


def test_dispose_asset_success(
    db,
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        retirement_date=date(2026, 8, 1),
    )

    disposed = dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason="Beyond economical repair",
        disposal_date=date(2026, 9, 1),
    )

    assert disposed.status == AssetStatus.DISPOSED
    assert disposed.is_active is False
    assert disposed.disposal_date == date(2026, 9, 1)
    assert disposed.disposal_reason == (
        "Beyond economical repair"
    )
    assert disposed.assigned_to_id is None

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.STATUS_CHANGE,
    )

    assert len(logs) == 2
    assert logs[-1].user_id == user.id
    assert logs[-1].new_value["status"] == (
        AssetStatus.DISPOSED.value
    )


def test_dispose_asset_defaults_to_today(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    disposed = dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason="Routine disposal",
    )

    assert disposed.disposal_date == date.today()


def test_dispose_asset_requires_retirement(
    clinic,
    user,
    asset,
):
    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="No longer required",
        )


def test_dispose_asset_rejects_already_disposed(
    clinic,
    user,
    asset,
):
    asset.status = AssetStatus.DISPOSED
    asset.is_active = False
    asset.retirement_date = date.today()

    with pytest.raises(ConflictError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="Already disposed",
        )


def test_dispose_asset_rejects_missing_reason(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason=None,
        )


def test_dispose_asset_rejects_empty_reason(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="",
        )


def test_dispose_asset_rejects_blank_reason(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="   ",
        )


def test_dispose_asset_rejects_non_string_reason(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason=123,
        )


def test_dispose_asset_normalizes_reason(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    disposed = dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason=(
            "   Damaged beyond repair   "
        ),
    )

    assert disposed.disposal_reason == (
        "Damaged beyond repair"
    )


def test_dispose_asset_rejects_reason_over_500_chars(
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="x" * 501,
        )


def test_dispose_asset_rejects_before_retirement_date(
    clinic,
    user,
    asset,
):
    retirement_date = date(2026, 8, 1)

    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        retirement_date=retirement_date,
    )

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="Invalid disposal date",
            disposal_date=date(2026, 7, 31),
        )


def test_dispose_asset_rejects_wrong_clinic(
    clinic,
    make_clinic,
    user,
    asset,
):
    other_clinic = make_clinic(
        name="Wrong Disposal Clinic",
    )

    asset.retirement_date = date.today()

    with pytest.raises(NotFoundError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=other_clinic.id,
            actor_user_id=user.id,
            disposal_reason="Wrong clinic",
        )


def test_dispose_asset_rejects_inactive_clinic(
    db,
    clinic,
    user,
    asset,
):
    asset.retirement_date = date.today()

    clinic.status = ClinicStatus.INACTIVE
    db.session.flush()

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="Should fail",
        )


def test_dispose_asset_releases_staff_assignment(
    clinic,
    user,
    asset,
    make_staff,
):
    staff = make_staff(
        clinic=clinic,
        status=StaffStatus.ACTIVE,
    )

    asset.assigned_to_id = staff.id

    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    disposed = dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason="Disposed asset",
    )

    assert disposed.assigned_to_id is None


@pytest.mark.parametrize(
    "actor_user_id",
    [0, -1, True, False, "1", None],
)
def test_dispose_asset_rejects_invalid_actor_id(
    clinic,
    asset,
    actor_user_id,
):
    asset.retirement_date = date.today()

    with pytest.raises(ValidationError):
        dispose_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=actor_user_id,
            disposal_reason="Should fail",
        )


# =============================================================================
# AUDIT / LIFECYCLE
# =============================================================================


def test_retire_audit_contains_old_and_new_values(
    db,
    clinic,
    user,
    asset,
):
    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        retirement_date=date(2026, 8, 1),
    )

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.STATUS_CHANGE,
    )

    assert len(logs) == 1

    audit = logs[0]

    assert audit.old_value["status"] == (
        AssetStatus.ACTIVE.value
    )
    assert audit.old_value["is_active"] is True
    assert audit.old_value["retirement_date"] is None

    assert audit.new_value["status"] == (
        AssetStatus.RETIRED.value
    )
    assert audit.new_value["is_active"] is False
    assert audit.new_value["retirement_date"] == (
        "2026-08-01"
    )


def test_dispose_audit_contains_old_and_new_values(
    db,
    clinic,
    user,
    asset,
):
    asset.assigned_to_id = None

    retirement_date = date(2026, 8, 1)

    retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        retirement_date=retirement_date,
    )

    dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason="Beyond repair",
        disposal_date=date(2026, 9, 1),
    )

    logs = audit_logs_for_asset(
        db,
        asset.id,
        AuditAction.STATUS_CHANGE,
    )

    assert len(logs) == 2

    audit = logs[-1]

    assert audit.old_value["status"] == (
        AssetStatus.RETIRED.value
    )
    assert audit.old_value["is_active"] is False
    assert audit.old_value["disposal_date"] is None
    assert audit.old_value["disposal_reason"] is None

    assert audit.new_value["status"] == (
        AssetStatus.DISPOSED.value
    )
    assert audit.new_value["is_active"] is False
    assert audit.new_value["disposal_date"] == (
        "2026-09-01"
    )
    assert audit.new_value["disposal_reason"] == (
        "Beyond repair"
    )


def test_full_asset_lifecycle(
    clinic,
    user,
):
    asset = create_asset(
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=create_schema(
            asset_tag="AST-FULL-LIFECYCLE",
            name="Lifecycle Asset",
        ),
    )

    assert asset.status == AssetStatus.ACTIVE
    assert asset.is_active is True

    updated = update_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        data=update_schema(
            name="Lifecycle Asset Updated",
        ),
    )

    assert updated.name == (
        "Lifecycle Asset Updated"
    )

    retired = retire_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    assert retired.status == AssetStatus.RETIRED
    assert retired.is_active is False

    disposed = dispose_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
        disposal_reason="End of useful life",
    )

    assert disposed.status == AssetStatus.DISPOSED
    assert disposed.is_active is False