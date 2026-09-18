from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

import app.modules.asset_control.services.asset_service as asset_service
from app.core.audit.models.audit_model import AuditLog
from app.core.enums.asset_enums import (
    AssetCategory,
    AssetCondition,
    AssetHistoryEventType,
    AssetOwnership,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.asset_control.models.asset_history_model import (
    AssetHistory,
)
from app.modules.asset_control.models.asset_model import Asset
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
)


def _asset_create_data(**overrides):
    data = {
        "asset_tag": "AST-CREATE-001",
        "name": "Infusion Pump",
        "category": AssetCategory.MEDICAL_EQUIPMENT,
        "condition": AssetCondition.GOOD,
        "ownership": AssetOwnership.CLINIC,
        "description": "  Portable infusion pump  ",
        "location": "  ICU 1  ",
        "serial_number": "  SN-001  ",
        "manufacturer": "  Acme Medical  ",
        "model_number": "  IP-100  ",
        "supplier": "  Acme Supplies  ",
        "notes": "  Initial stock  ",
        "purchase_date": date.today() - timedelta(days=30),
        "purchase_cost": Decimal("1250.50"),
        "warranty_expiry": date.today() + timedelta(days=335),
    }

    data.update(overrides)

    return data


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
        query = query.filter_by(action=action)

    return query.order_by(AuditLog.id.asc()).all()


class TestAssetValidationHelpers:
    def test_positive_id_accepts_positive_integer(self):
        assert (
            asset_service._validate_positive_id(
                7,
                "asset_id",
            )
            == 7
        )

    @pytest.mark.parametrize(
        "value",
        [
            True,
            False,
            0,
            -1,
            1.5,
            "1",
            None,
        ],
    )
    def test_positive_id_rejects_invalid_values(
        self,
        value,
    ):
        with pytest.raises(
            ValidationError,
            match="asset_id must be a positive integer",
        ):
            asset_service._validate_positive_id(
                value,
                "asset_id",
            )

    def test_normalize_optional_text_strips_and_converts_blank(
        self,
    ):
        assert (
            asset_service._normalize_optional_text(
                "  hello  "
            )
            == "hello"
        )

        assert (
            asset_service._normalize_optional_text(
                "   "
            )
            is None
        )

        assert (
            asset_service._normalize_optional_text(
                None
            )
            is None
        )

    def test_normalize_optional_text_rejects_non_string(
        self,
    ):
        with pytest.raises(
            ValidationError,
            match="Text field must be a string",
        ):
            asset_service._normalize_optional_text(123)

    def test_purchase_dates_reject_warranty_before_purchase(
        self,
    ):
        with pytest.raises(
            ValidationError,
            match=(
                "warranty_expiry cannot be before "
                "purchase_date"
            ),
        ):
            asset_service._validate_purchase_dates(
                purchase_date=date(2026, 9, 10),
                warranty_expiry=date(2026, 9, 9),
            )

    def test_purchase_dates_accept_valid_dates(self):
        asset_service._validate_purchase_dates(
            purchase_date=date(2026, 9, 10),
            warranty_expiry=date(2026, 9, 10),
        )

        asset_service._validate_purchase_dates(
            purchase_date=None,
            warranty_expiry=None,
        )

    def test_audit_value_normalizes_supported_types(self):
        assert (
            asset_service._audit_value(
                AssetStatus.ACTIVE
            )
            == "active"
        )

        assert (
            asset_service._audit_value(
                date(2026, 9, 18)
            )
            == "2026-09-18"
        )

        assert (
            asset_service._audit_value(
                Decimal("12.50")
            )
            == "12.50"
        )

        assert (
            asset_service._audit_value(None)
            is None
        )

        assert (
            asset_service._audit_value("plain")
            == "plain"
        )

    def test_build_audit_changes_normalizes_values(self):
        old_value, new_value = (
            asset_service._build_audit_changes(
                old_values={
                    "status": AssetStatus.ACTIVE,
                    "cost": Decimal("5.00"),
                },
                new_values={
                    "status": AssetStatus.ASSIGNED,
                    "cost": Decimal("7.50"),
                },
            )
        )

        assert old_value == {
            "status": "active",
            "cost": "5.00",
        }

        assert new_value == {
            "status": "assigned",
            "cost": "7.50",
        }


class TestCreateAsset:
    def test_creates_asset_with_normalized_fields_and_history(
        self,
        db,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        asset = asset_service.create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=_asset_create_data(),
        )

        assert asset.id is not None
        assert asset.clinic_id == clinic.id
        assert asset.status == AssetStatus.ACTIVE
        assert (
            asset.maintenance_status
            == MaintenanceStatus.NOT_REQUIRED
        )
        assert asset.is_active is True
        assert (
            asset.description
            == "Portable infusion pump"
        )
        assert asset.location == "ICU 1"
        assert asset.serial_number == "SN-001"
        assert asset.manufacturer == "Acme Medical"
        assert asset.model_number == "IP-100"
        assert asset.supplier == "Acme Supplies"
        assert asset.notes == "Initial stock"

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.CREATED,
            )
        ).scalar_one()

        assert history.clinic_id == clinic.id
        assert history.actor_user_id == user.id
        assert history.new_status == AssetStatus.ACTIVE
        assert history.new_condition == AssetCondition.GOOD
        assert history.new_location == "ICU 1"
        assert (
            history.event_metadata["asset_tag"]
            == asset.asset_tag
        )

        audit.assert_called_once()

        assert (
            audit.call_args.kwargs["action"]
            == AuditAction.CREATE
        )

        assert (
            audit.call_args.kwargs["entity_type"]
            == "Asset"
        )

        assert (
            audit.call_args.kwargs["entity_id"]
            == asset.id
        )

    def test_accepts_schema_instance(
        self,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        data = AssetCreateSchema.model_validate(
            _asset_create_data(
                asset_tag="AST-SCHEMA-001",
                description="schema input",
            )
        )

        asset = asset_service.create_asset(
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=data,
        )

        assert (
            asset.asset_tag
            == "AST-SCHEMA-001"
        )

        assert (
            asset.description
            == "schema input"
        )

    def test_rejects_duplicate_tag_in_same_clinic(
        self,
        clinic,
        user,
        make_asset,
        monkeypatch,
    ):
        make_asset(
            clinic,
            asset_tag="AST-DUP-001",
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Asset tag 'AST-DUP-001' "
                "is already in use"
            ),
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_asset_create_data(
                    asset_tag="AST-DUP-001",
                ),
            )

    def test_allows_same_tag_in_different_clinics(
        self,
        make_clinic,
        make_user,
        make_asset,
        monkeypatch,
    ):
        clinic_a = make_clinic(
            name="Asset Clinic A"
        )

        clinic_b = make_clinic(
            name="Asset Clinic B"
        )

        user_b = make_user(clinic_b)

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        make_asset(
            clinic_a,
            asset_tag="AST-SHARED-001",
        )

        asset = asset_service.create_asset(
            clinic_id=clinic_b.id,
            actor_user_id=user_b.id,
            data=_asset_create_data(
                asset_tag="AST-SHARED-001",
            ),
        )

        assert asset.clinic_id == clinic_b.id

    def test_rejects_missing_clinic(
        self,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match="Clinic 999999 not found",
        ):
            asset_service.create_asset(
                clinic_id=999999,
                actor_user_id=user.id,
                data=_asset_create_data(),
            )

    def test_rejects_inactive_clinic(
        self,
        suspended_clinic,
        make_user,
        monkeypatch,
    ):
        inactive_user = make_user(
            suspended_clinic
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                f"Clinic {suspended_clinic.id} "
                "is not active"
            ),
        ):
            asset_service.create_asset(
                clinic_id=suspended_clinic.id,
                actor_user_id=inactive_user.id,
                data=_asset_create_data(),
            )

    def test_rejects_missing_actor(
        self,
        clinic,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match="Authenticated user not found",
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=999999,
                data=_asset_create_data(),
            )

    def test_rejects_inactive_actor(
        self,
        clinic,
        make_user,
        monkeypatch,
    ):
        inactive_user = make_user(
            clinic,
            is_active=False,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                f"Authenticated user "
                f"{inactive_user.id} is inactive"
            ),
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=inactive_user.id,
                data=_asset_create_data(),
            )

    def test_rejects_actor_from_another_clinic(
        self,
        clinic,
        make_clinic,
        make_user,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Asset Clinic"
        )

        other_user = make_user(
            other_clinic
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match="Authenticated user not found",
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=other_user.id,
                data=_asset_create_data(),
            )

    def test_rejects_invalid_purchase_warranty_order(
        self,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            PydanticValidationError,
            match=(
                "warranty_expiry cannot be before "
                "purchase_date"
            ),
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_asset_create_data(
                    purchase_date=date(
                        2026,
                        9,
                        20,
                    ),
                    warranty_expiry=date(
                        2026,
                        9,
                        19,
                    ),
                ),
            )

    def test_rolls_back_when_audit_fails(
        self,
        db,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(
                side_effect=RuntimeError(
                    "audit failed"
                )
            ),
        )

        with pytest.raises(
            RuntimeError,
            match="audit failed",
        ):
            asset_service.create_asset(
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_asset_create_data(
                    asset_tag="AST-ROLLBACK-001"
                ),
            )

        db.session.expire_all()

        persisted = db.session.execute(
            db.select(Asset).where(
                Asset.asset_tag
                == "AST-ROLLBACK-001"
            )
        ).scalar_one_or_none()

        assert persisted is None


class TestGetAsset:
    def test_returns_asset_from_same_clinic(
        self,
        asset,
        clinic,
    ):
        result = asset_service.get_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
        )

        assert result.id == asset.id

    def test_rejects_invalid_asset_id(
        self,
        clinic,
        asset,
    ):
        with pytest.raises(
            ValidationError,
            match=(
                "asset_id must be a positive integer"
            ),
        ):
            asset_service.get_asset(
                asset_id=0,
                clinic_id=clinic.id,
            )

    def test_rejects_invalid_clinic_id(
        self,
        asset,
    ):
        with pytest.raises(
            ValidationError,
            match=(
                "clinic_id must be a positive integer"
            ),
        ):
            asset_service.get_asset(
                asset_id=asset.id,
                clinic_id=0,
            )

    def test_hides_asset_from_other_clinic(
        self,
        asset,
        make_clinic,
    ):
        other_clinic = make_clinic(
            name="Other Clinic"
        )

        with pytest.raises(
            NotFoundError,
            match=f"Asset {asset.id} not found",
        ):
            asset_service.get_asset(
                asset_id=asset.id,
                clinic_id=other_clinic.id,
            )

    def test_missing_asset_raises_not_found(
        self,
        clinic,
    ):
        with pytest.raises(
            NotFoundError,
            match="Asset 999999 not found",
        ):
            asset_service.get_asset(
                asset_id=999999,
                clinic_id=clinic.id,
            )


class TestListAssets:
    def test_lists_assets_with_pagination(
        self,
        clinic,
        make_asset,
    ):
        for index in range(3):
            make_asset(
                clinic,
                asset_tag=f"AST-LIST-{index}",
                name=f"List Asset {index}",
            )

        result = asset_service.list_assets(
            clinic_id=clinic.id,
            query={
                "page": 1,
                "per_page": 2,
            },
        )

        assert result["page"] == 1
        assert result["per_page"] == 2
        assert result["total"] == 3
        assert result["pages"] == 2
        assert result["has_next"] is True
        assert result["has_prev"] is False
        assert len(result["items"]) == 2

    def test_filters_by_search(
        self,
        clinic,
        make_asset,
    ):
        make_asset(
            clinic,
            asset_tag="AST-PUMP-001",
            name="Infusion Pump",
            serial_number="SN-PUMP-001",
            manufacturer="Acme",
            model_number="MODEL-X",
            location="ICU",
        )

        make_asset(
            clinic,
            asset_tag="AST-WHEEL-001",
            name="Wheelchair",
            serial_number="SN-WHEEL-001",
            manufacturer="Mobility",
            model_number="MODEL-Y",
            location="Ward",
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={"search": "pump"},
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "search": "SN-PUMP-001"
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={"search": "Acme"},
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "search": "MODEL-X"
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={"search": "ICU"},
            )["total"]
            == 1
        )

    def test_filters_by_state_fields(
        self,
        clinic,
        staff,
        make_asset,
    ):
        changed_condition = next(
            condition
            for condition in AssetCondition
            if condition != AssetCondition.GOOD
        )

        make_asset(
            clinic,
            asset_tag="AST-FILTER-001",
            status=AssetStatus.ACTIVE,
            condition=changed_condition,
            maintenance_status=(
                MaintenanceStatus.NOT_REQUIRED
            ),
            assigned_to_id=staff.id,
            is_active=True,
        )

        make_asset(
            clinic,
            asset_tag="AST-FILTER-002",
            status=AssetStatus.UNDER_MAINTENANCE,
            condition=AssetCondition.GOOD,
            maintenance_status=(
                MaintenanceStatus.IN_PROGRESS
            ),
            is_active=False,
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "condition": changed_condition
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "status":
                        AssetStatus.UNDER_MAINTENANCE
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "maintenance_status":
                        MaintenanceStatus.IN_PROGRESS
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "assigned_to_id": staff.id
                },
            )["total"]
            == 1
        )

        assert (
            asset_service.list_assets(
                clinic_id=clinic.id,
                query={
                    "is_active": False
                },
            )["total"]
            == 1
        )

    def test_does_not_return_other_clinic_assets(
        self,
        clinic,
        make_clinic,
        make_asset,
    ):
        other_clinic = make_clinic(
            name="Other List Clinic"
        )

        make_asset(
            clinic,
            asset_tag="AST-LOCAL",
        )

        make_asset(
            other_clinic,
            asset_tag="AST-OTHER",
        )

        result = asset_service.list_assets(
            clinic_id=clinic.id,
        )

        assert result["total"] == 1

        assert (
            result["items"][0].clinic_id
            == clinic.id
        )


class TestUpdateAsset:
    def test_updates_text_fields(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        original_name = asset.name

        result = asset_service.update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "name": "  Updated Pump  ",
                "description":
                    "  Updated description  ",
                "manufacturer":
                    "  Updated Manufacturer  ",
                "notes":
                    "  Updated notes  ",
            },
        )

        assert result.name == "Updated Pump"
        assert (
            result.description
            == "Updated description"
        )
        assert (
            result.manufacturer
            == "Updated Manufacturer"
        )
        assert result.notes == "Updated notes"

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.UPDATED,
            )
        ).scalar_one()

        assert (
            history.event_metadata["old"]["name"]
            == original_name
        )

        audit.assert_called_once()

        assert (
            audit.call_args.kwargs["action"]
            == AuditAction.UPDATE
        )

    def test_records_condition_and_location_history(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        changed_condition = next(
            condition
            for condition in AssetCondition
            if condition != asset.condition
        )

        result = asset_service.update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "condition": changed_condition,
                "location": "Radiology",
            },
        )

        assert (
            result.condition
            == changed_condition
        )

        assert result.location == "Radiology"

        histories = db.session.execute(
            db.select(AssetHistory)
            .where(
                AssetHistory.asset_id == asset.id,
            )
            .order_by(
                AssetHistory.id.asc()
            )
        ).scalars().all()

        types = [
            history.event_type
            for history in histories
        ]

        assert (
            AssetHistoryEventType.CONDITION_CHANGED
            in types
        )

        assert (
            AssetHistoryEventType.LOCATION_CHANGED
            in types
        )

        condition_history = next(
            history
            for history in histories
            if history.event_type
            == AssetHistoryEventType.CONDITION_CHANGED
        )

        location_history = next(
            history
            for history in histories
            if history.event_type
            == AssetHistoryEventType.LOCATION_CHANGED
        )

        assert (
            condition_history.previous_condition
            == AssetCondition.GOOD
        )

        assert (
            condition_history.new_condition
            == changed_condition
        )

        assert (
            location_history.previous_location
            is None
        )

        assert (
            location_history.new_location
            == "Radiology"
        )

    def test_ignores_fields_that_do_not_change(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        result = asset_service.update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "name": asset.name,
            },
        )

        assert result.id == asset.id
        audit.assert_not_called()

    def test_rejects_empty_update(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match="No fields provided for update",
        ):
            asset_service.update_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={},
            )

    def test_rejects_terminal_asset_update(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        terminal = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {terminal.id} "
                "is no longer editable"
            ),
        ):
            asset_service.update_asset(
                asset_id=terminal.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "name": "Should Fail"
                },
            )

    def test_rejects_duplicate_asset_tag(
        self,
        make_asset,
        clinic,
        asset,
        user,
        monkeypatch,
    ):
        other = make_asset(
            clinic,
            asset_tag="AST-EXISTING-001",
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Asset tag "
                "'AST-EXISTING-001' "
                "is already in use"
            ),
        ):
            asset_service.update_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "asset_tag":
                        other.asset_tag
                },
            )

    def test_accepts_same_asset_tag(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        result = asset_service.update_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "asset_tag": asset.asset_tag
            },
        )

        assert (
            result.asset_tag
            == asset.asset_tag
        )

        audit.assert_not_called()

    def test_rejects_invalid_purchase_warranty_order(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            PydanticValidationError,
            match=(
                "warranty_expiry cannot be before "
                "purchase_date"
            ),
        ):
            asset_service.update_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "purchase_date": date(
                        2026,
                        9,
                        20,
                    ),
                    "warranty_expiry": date(
                        2026,
                        9,
                        19,
                    ),
                },
            )

    def test_hides_update_target_across_clinics(
        self,
        asset,
        make_clinic,
        make_user,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Update Clinic"
        )

        other_user = make_user(
            other_clinic
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=f"Asset {asset.id} not found",
        ):
            asset_service.update_asset(
                asset_id=asset.id,
                clinic_id=other_clinic.id,
                actor_user_id=other_user.id,
                data={
                    "name": "Cross Clinic"
                },
            )

    def test_rolls_back_when_history_fails(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        original_name = asset.name

        db.session.commit()

        monkeypatch.setattr(
            asset_service,
            "record_asset_history",
            Mock(
                side_effect=RuntimeError(
                    "history failed"
                )
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            RuntimeError,
            match="history failed",
        ):
            asset_service.update_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "name": "Rollback Name"
                },
            )

        db.session.expire_all()

        persisted = db.session.get(
            Asset,
            asset.id,
        )

        assert persisted is not None
        assert (
            persisted.name
            == original_name
        )


class TestRetireAsset:
    def test_retires_asset_and_records_history(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        retirement_date = date(
            2026,
            9,
            18,
        )

        result = asset_service.retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            retirement_date=retirement_date,
        )

        assert (
            result.status
            == AssetStatus.RETIRED
        )

        assert result.is_active is False

        assert (
            result.retirement_date
            == retirement_date
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.RETIRED,
            )
        ).scalar_one()

        assert (
            history.previous_status
            == AssetStatus.ACTIVE
        )

        assert (
            history.new_status
            == AssetStatus.RETIRED
        )

        assert (
            history.reason
            == "Asset retired"
        )

        assert (
            history.event_metadata[
                "retirement_date"
            ]
            == "2026-09-18"
        )

        audit.assert_called_once()

    def test_default_retirement_date_is_today(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        result = asset_service.retire_asset(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )

        assert (
            result.retirement_date
            == date.today()
        )

    def test_rejects_already_retired_asset(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {retired.id} "
                "is already retired"
            ),
        ):
            asset_service.retire_asset(
                asset_id=retired.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_rejects_disposed_asset(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        disposed = make_asset(
            clinic,
            status=AssetStatus.DISPOSED,
            is_active=False,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {disposed.id} "
                "has already been disposed"
            ),
        ):
            asset_service.retire_asset(
                asset_id=disposed.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_rejects_assigned_asset(
        self,
        asset,
        staff,
        clinic,
        user,
        monkeypatch,
    ):
        asset.assigned_to_id = staff.id

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Assigned assets must be "
                "returned before retirement"
            ),
        ):
            asset_service.retire_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    @pytest.mark.parametrize(
        "maintenance_status",
        [
            MaintenanceStatus.SCHEDULED,
            MaintenanceStatus.DUE,
            MaintenanceStatus.IN_PROGRESS,
            MaintenanceStatus.OVERDUE,
        ],
    )
    def test_rejects_active_maintenance(
        self,
        make_asset,
        clinic,
        user,
        maintenance_status,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            maintenance_status=maintenance_status,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Active maintenance must be "
                "resolved before retirement"
            ),
        ):
            asset_service.retire_asset(
                asset_id=candidate.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_rejects_retirement_before_purchase_date(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            purchase_date=date(
                2026,
                9,
                20,
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                "retirement_date cannot be "
                "before purchase_date"
            ),
        ):
            asset_service.retire_asset(
                asset_id=candidate.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                retirement_date=date(
                    2026,
                    9,
                    19,
                ),
            )


class TestDisposeAsset:
    def test_disposes_retired_asset(
        self,
        db,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
        )

        audit = Mock()

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            audit,
        )

        result = asset_service.dispose_asset(
            asset_id=retired.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="  End of life  ",
            disposal_date=date(
                2026,
                9,
                18,
            ),
        )

        assert (
            result.status
            == AssetStatus.DISPOSED
        )

        assert result.is_active is False

        assert (
            result.disposal_reason
            == "End of life"
        )

        assert (
            result.disposal_date
            == date(2026, 9, 18)
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == retired.id,
                AssetHistory.event_type
                == AssetHistoryEventType.DISPOSED,
            )
        ).scalar_one()

        assert history.reason == "End of life"

        assert (
            history.new_status
            == AssetStatus.DISPOSED
        )

        audit.assert_called_once()

    def test_default_disposal_date_is_today(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date.today(),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        result = asset_service.dispose_asset(
            asset_id=retired.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason="Scrapped",
        )

        assert (
            result.disposal_date
            == date.today()
        )

    def test_rejects_already_disposed_asset(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        disposed = make_asset(
            clinic,
            status=AssetStatus.DISPOSED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {disposed.id} "
                "is already disposed"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=disposed.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Already disposed",
            )

    def test_requires_retirement(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                "Asset must be retired "
                "before disposal"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Scrapped",
            )

    @pytest.mark.parametrize(
        "reason",
        [
            None,
            "",
            "   ",
        ],
    )
    def test_requires_non_blank_disposal_reason(
        self,
        make_asset,
        clinic,
        user,
        reason,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match="disposal_reason is required",
        ):
            asset_service.dispose_asset(
                asset_id=retired.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason=reason,
            )

    def test_rejects_assigned_asset(
        self,
        make_asset,
        staff,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
            assigned_to_id=staff.id,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Assigned assets must be "
                "returned before disposal"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=retired.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Scrapped",
            )

    @pytest.mark.parametrize(
        "maintenance_status",
        [
            MaintenanceStatus.SCHEDULED,
            MaintenanceStatus.DUE,
            MaintenanceStatus.IN_PROGRESS,
            MaintenanceStatus.OVERDUE,
        ],
    )
    def test_rejects_active_maintenance(
        self,
        make_asset,
        clinic,
        user,
        maintenance_status,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
            maintenance_status=maintenance_status,
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                "Active maintenance must be "
                "resolved before disposal"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=retired.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Scrapped",
            )

    def test_rejects_disposal_before_retirement(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                20,
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                "disposal_date cannot be "
                "before retirement_date"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=retired.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Scrapped",
                disposal_date=date(
                    2026,
                    9,
                    19,
                ),
            )

    def test_normalizes_disposal_reason(
        self,
        make_asset,
        clinic,
        user,
        monkeypatch,
    ):
        retired = make_asset(
            clinic,
            status=AssetStatus.RETIRED,
            is_active=False,
            retirement_date=date(
                2026,
                9,
                10,
            ),
        )

        monkeypatch.setattr(
            asset_service,
            "create_audit_log",
            Mock(),
        )

        result = asset_service.dispose_asset(
            asset_id=retired.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            disposal_reason=(
                "   Damaged beyond repair   "
            ),
        )

        assert (
            result.disposal_reason
            == "Damaged beyond repair"
        )

    def test_rejects_wrong_clinic(
        self,
        clinic,
        make_clinic,
        user,
        asset,
    ):
        other_clinic = make_clinic(
            name="Wrong Disposal Clinic"
        )

        asset.retirement_date = date.today()

        with pytest.raises(
            NotFoundError,
        ):
            asset_service.dispose_asset(
                asset_id=asset.id,
                clinic_id=other_clinic.id,
                actor_user_id=user.id,
                disposal_reason="Wrong clinic",
            )

    def test_rejects_inactive_clinic(
        self,
        db,
        clinic,
        user,
        asset,
    ):
        asset.retirement_date = date.today()

        clinic.status = ClinicStatus.SUSPENDED
        db.session.flush()

        with pytest.raises(
            ValidationError,
            match=(
                f"Clinic {clinic.id} is not active"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                disposal_reason="Should fail",
            )

    @pytest.mark.parametrize(
        "actor_user_id",
        [
            0,
            -1,
            True,
            False,
            "1",
            None,
        ],
    )
    def test_rejects_invalid_actor_id(
        self,
        clinic,
        asset,
        actor_user_id,
    ):
        asset.retirement_date = date.today()

        with pytest.raises(
            ValidationError,
            match=(
                "actor_user_id must be "
                "a positive integer"
            ),
        ):
            asset_service.dispose_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=actor_user_id,
                disposal_reason="Should fail",
            )