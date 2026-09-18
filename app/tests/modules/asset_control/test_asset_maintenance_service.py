from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

import app.modules.asset_control.services.asset_maintenance_service as maintenance_service
from app.core.enums.asset_enums import (
    AssetHistoryEventType,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.asset_control.models.asset_history_model import (
    AssetHistory,
)
from app.modules.asset_control.models.asset_maintenance_model import (
    AssetMaintenance,
)
from app.modules.asset_control.models.asset_model import Asset
from app.modules.asset_control.schemas.asset_maintenance_schema import (
    AssetMaintenanceListQuerySchema,
)


def _schedule_data(**overrides):
    data = {
        "scheduled_date": date(
            2026,
            9,
            20,
        ),
        "description": "Preventive maintenance",
        "notes": "Routine inspection",
    }

    data.update(overrides)

    return data


def _schedule(
    *,
    asset,
    clinic,
    user,
    monkeypatch,
):
    monkeypatch.setattr(
        maintenance_service,
        "create_audit_log",
        Mock(),
    )

    return (
        maintenance_service.schedule_maintenance(
            asset_id=asset.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data=_schedule_data(),
        )
    )


def _start(
    *,
    asset,
    clinic,
    user,
    monkeypatch,
):
    maintenance = _schedule(
        asset=asset,
        clinic=clinic,
        user=user,
        monkeypatch=monkeypatch,
    )

    maintenance_service.start_maintenance(
        maintenance_id=maintenance.id,
        clinic_id=clinic.id,
        actor_user_id=user.id,
    )

    return maintenance


class TestScheduleMaintenance:
    def test_schedules_maintenance(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            audit,
        )

        result = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )
        )

        assert result.id is not None
        assert (
            result.status
            == MaintenanceStatus.SCHEDULED
        )
        assert (
            result.scheduled_date
            == date(2026, 9, 20)
        )

        assert (
            result.description
            == "Preventive maintenance"
        )

        assert (
            result.notes
            == "Routine inspection"
        )

        db.session.expire(asset)

        assert (
            asset.maintenance_status
            == MaintenanceStatus.SCHEDULED
        )

        assert (
            asset.next_maintenance_date
            == date(2026, 9, 20)
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.UPDATED,
            )
        ).scalar_one()

        assert (
            history.event_metadata[
                "maintenance_id"
            ]
            == result.id
        )

        assert (
            history.event_metadata[
                "maintenance_status"
            ]
            == MaintenanceStatus.SCHEDULED.value
        )

        audit.assert_called_once()

    def test_accepts_schema_instance(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        schema = (
            maintenance_service
            .AssetMaintenanceScheduleSchema(
                scheduled_date=date(
                    2026,
                    9,
                    25,
                ),
                description="Schema schedule",
            )
        )

        result = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=schema,
            )
        )

        assert (
            result.scheduled_date
            == date(2026, 9, 25)
        )

        assert (
            result.description
            == "Schema schedule"
        )

    @pytest.mark.parametrize(
        "status",
        [
            AssetStatus.RETIRED,
            AssetStatus.DISPOSED,
            AssetStatus.LOST,
        ],
    )
    def test_rejects_terminal_assets(
        self,
        make_asset,
        clinic,
        user,
        status,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            asset_tag=(
                f"AST-MAINT-{status.value}"
            ),
            status=status,
            is_active=False,
        )

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {candidate.id} "
                "cannot be scheduled for maintenance"
            ),
        ):
            maintenance_service.schedule_maintenance(
                asset_id=candidate.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )

    def test_rejects_existing_active_maintenance(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        first = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )
        )

        assert (
            first.status
            == MaintenanceStatus.SCHEDULED
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {asset.id} "
                "already has active maintenance"
            ),
        ):
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(
                    scheduled_date=date(
                        2026,
                        9,
                        22,
                    )
                ),
            )

    def test_hides_cross_clinic_asset(
        self,
        asset,
        make_clinic,
        make_user,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Maintenance Clinic"
        )

        other_user = make_user(
            other_clinic
        )

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset {asset.id} not found"
            ),
        ):
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=other_clinic.id,
                actor_user_id=other_user.id,
                data=_schedule_data(),
            )


class TestStartMaintenance:
    def test_starts_scheduled_maintenance(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = _schedule(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        result = (
            maintenance_service.start_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "notes": "Started now"
                },
            )
        )

        assert (
            result.status
            == MaintenanceStatus.IN_PROGRESS
        )

        assert result.started_at is not None

        assert (
            result.performed_by_user_id
            == user.id
        )

        assert (
            result.notes
            == "Started now"
        )

        db.session.expire(asset)

        assert (
            asset.status
            == AssetStatus.UNDER_MAINTENANCE
        )

        assert (
            asset.maintenance_status
            == MaintenanceStatus.IN_PROGRESS
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.MAINTENANCE_STARTED,
            )
        ).scalar_one()

        assert (
            history.previous_status
            == AssetStatus.ACTIVE
        )

        assert (
            history.new_status
            == AssetStatus.UNDER_MAINTENANCE
        )

        assert (
            history.event_metadata[
                "previous_asset_status"
            ]
            == AssetStatus.ACTIVE.value
        )

    @pytest.mark.parametrize(
        "status",
        [
            MaintenanceStatus.COMPLETED,
            MaintenanceStatus.CANCELLED,
        ],
    )
    def test_rejects_invalid_start_status(
        self,
        db,
        asset,
        clinic,
        user,
        status,
        monkeypatch,
    ):
        maintenance = AssetMaintenance(
            clinic_id=clinic.id,
            asset_id=asset.id,
            status=status,
            scheduled_date=date(
                2026,
                9,
                20,
            ),
            description="Test",
        )

        db.session.add(maintenance)
        db.session.flush()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Maintenance {maintenance.id} "
                "cannot be started from status "
                f"{status.value}"
            ),
        ):
            maintenance_service.start_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    @pytest.mark.parametrize(
        "asset_status",
        [
            AssetStatus.RETIRED,
            AssetStatus.DISPOSED,
            AssetStatus.LOST,
        ],
    )
    def test_rejects_terminal_asset(
        self,
        db,
        make_asset,
        clinic,
        user,
        asset_status,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            asset_tag=(
                f"AST-START-{asset_status.value}"
            ),
            status=asset_status,
            is_active=False,
        )

        maintenance = AssetMaintenance(
            clinic_id=clinic.id,
            asset_id=candidate.id,
            status=MaintenanceStatus.SCHEDULED,
            scheduled_date=date(
                2026,
                9,
                20,
            ),
            description="Test",
        )

        db.session.add(maintenance)
        db.session.flush()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {candidate.id} "
                "cannot enter maintenance"
            ),
        ):
            maintenance_service.start_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    @pytest.mark.parametrize(
        "status",
        [
            MaintenanceStatus.DUE,
            MaintenanceStatus.OVERDUE,
        ],
    )
    def test_starts_due_and_overdue(
        self,
        db,
        make_asset,
        clinic,
        user,
        status,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            asset_tag=(
                f"AST-DUE-{status.value}"
            ),
        )

        maintenance = AssetMaintenance(
            clinic_id=clinic.id,
            asset_id=candidate.id,
            status=status,
            scheduled_date=date(
                2026,
                9,
                20,
            ),
            description="Test",
        )

        db.session.add(maintenance)
        db.session.flush()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        result = (
            maintenance_service.start_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )
        )

        assert (
            result.status
            == MaintenanceStatus.IN_PROGRESS
        )


class TestCompleteMaintenance:
    def test_completes_and_restores_active_status(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = _start(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        result = (
            maintenance_service.complete_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "cost": "125.50",
                    "notes":
                        "Completed successfully",
                },
            )
        )

        assert (
            result.status
            == MaintenanceStatus.COMPLETED
        )

        assert result.completed_at is not None

        assert (
            result.performed_by_user_id
            == user.id
        )

        assert result.cost == Decimal("125.50")

        assert (
            result.notes
            == "Completed successfully"
        )

        db.session.expire(asset)

        assert (
            asset.status
            == AssetStatus.ACTIVE
        )

        assert (
            asset.maintenance_status
            == MaintenanceStatus.COMPLETED
        )

        assert (
            asset.last_maintenance_date
            == result.completed_at.date()
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.MAINTENANCE_COMPLETED,
            )
        ).scalar_one()

        assert (
            history.previous_status
            == AssetStatus.UNDER_MAINTENANCE
        )

        assert (
            history.new_status
            == AssetStatus.ACTIVE
        )

    def test_restores_assigned_status(
        self,
        db,
        make_asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            asset_tag="AST-RESTORE-ASSIGNED",
            status=AssetStatus.ASSIGNED,
            assigned_to_id=staff.id,
        )

        maintenance = _start(
            asset=candidate,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        result = (
            maintenance_service.complete_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )
        )

        assert (
            result.status
            == MaintenanceStatus.COMPLETED
        )

        db.session.expire(candidate)

        assert (
            candidate.status
            == AssetStatus.ASSIGNED
        )

        assert (
            candidate.assigned_to_id
            == staff.id
        )

    def test_rejects_completion_from_wrong_status(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = AssetMaintenance(
            clinic_id=clinic.id,
            asset_id=asset.id,
            status=MaintenanceStatus.SCHEDULED,
            scheduled_date=date(
                2026,
                9,
                20,
            ),
            description="Test",
        )

        db.session.add(maintenance)
        db.session.flush()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Maintenance {maintenance.id} "
                "cannot be completed from status "
                f"{MaintenanceStatus.SCHEDULED.value}"
            ),
        ):
            maintenance_service.complete_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_falls_back_to_active_when_previous_status_metadata_is_invalid(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = _start(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.MAINTENANCE_STARTED,
            )
        ).scalar_one()

        history.event_metadata = {
            "previous_asset_status":
                "not-a-real-status"
        }

        db.session.flush()

        result = (
            maintenance_service.complete_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )
        )

        assert (
            result.status
            == MaintenanceStatus.COMPLETED
        )

        db.session.expire(asset)

        assert (
            asset.status
            == AssetStatus.ACTIVE
        )

    def test_rolls_back_completion_when_history_fails(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = _start(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        original_cost = maintenance.cost

        monkeypatch.setattr(
            maintenance_service,
            "record_asset_history",
            Mock(
                side_effect=RuntimeError(
                    "history failed"
                )
            ),
        )

        with pytest.raises(
            RuntimeError,
            match="history failed",
        ):
            maintenance_service.complete_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "cost": "99.99"
                },
            )

        db.session.expire_all()

        persisted = db.session.get(
            AssetMaintenance,
            maintenance.id,
        )

        persisted_asset = db.session.get(
            Asset,
            asset.id,
        )

        assert (
            persisted.status
            == MaintenanceStatus.IN_PROGRESS
        )

        assert (
            persisted.cost
            == original_cost
        )

        assert (
            persisted.completed_at
            is None
        )

        assert (
            persisted_asset.status
            == AssetStatus.UNDER_MAINTENANCE
        )


class TestCancelMaintenance:
    def test_cancels_scheduled_maintenance(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        maintenance = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )
        )

        result = (
            maintenance_service.cancel_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "reason":
                        "Vendor cancelled visit"
                },
            )
        )

        assert (
            result.status
            == MaintenanceStatus.CANCELLED
        )

        assert (
            result.notes
            == "Cancelled: Vendor cancelled visit"
        )

        db.session.expire(asset)

        assert (
            asset.status
            == AssetStatus.ACTIVE
        )

        assert (
            asset.maintenance_status
            == MaintenanceStatus.CANCELLED
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.MAINTENANCE_CANCELLED,
            )
        ).scalar_one()

        assert (
            history.reason
            == "Vendor cancelled visit"
        )

    def test_cancels_in_progress_and_restores_previous_status(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = _start(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        result = (
            maintenance_service.cancel_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "reason":
                        "Emergency work postponed"
                },
            )
        )

        assert (
            result.status
            == MaintenanceStatus.CANCELLED
        )

        assert (
            result.notes
            == "Cancelled: Emergency work postponed"
        )

        assert (
            asset.status
            == AssetStatus.ACTIVE
        )

        assert (
            asset.maintenance_status
            == MaintenanceStatus.CANCELLED
        )

    @pytest.mark.parametrize(
        "status",
        [
            MaintenanceStatus.COMPLETED,
            MaintenanceStatus.CANCELLED,
        ],
    )
    def test_rejects_cancellation_from_terminal_status(
        self,
        db,
        asset,
        clinic,
        user,
        status,
        monkeypatch,
    ):
        maintenance = AssetMaintenance(
            clinic_id=clinic.id,
            asset_id=asset.id,
            status=status,
            scheduled_date=date(
                2026,
                9,
                20,
            ),
            description="Test",
        )

        db.session.add(maintenance)
        db.session.flush()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Maintenance {maintenance.id} "
                "cannot be cancelled from status "
                f"{status.value}"
            ),
        ):
            maintenance_service.cancel_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "reason":
                        "No longer needed"
                },
            )

    def test_rolls_back_cancellation_when_history_fails(
        self,
        db,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        maintenance = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )
        )

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            Mock(),
        )

        monkeypatch.setattr(
            maintenance_service,
            "record_asset_history",
            Mock(
                side_effect=RuntimeError(
                    "history failed"
                )
            ),
        )

        with pytest.raises(
            RuntimeError,
            match="history failed",
        ):
            maintenance_service.cancel_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "reason":
                        "Will rollback"
                },
            )

        db.session.expire_all()

        persisted = db.session.get(
            AssetMaintenance,
            maintenance.id,
        )

        persisted_asset = db.session.get(
            Asset,
            asset.id,
        )

        assert (
            persisted.status
            == MaintenanceStatus.SCHEDULED
        )

        assert (
            persisted.notes
            == "Routine inspection"
        )

        assert (
            persisted_asset.status
            == AssetStatus.ACTIVE
        )

        assert (
            persisted_asset.maintenance_status
            == MaintenanceStatus.SCHEDULED
        )

    def test_cancel_audit_preserves_pre_cancel_status(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            maintenance_service,
            "create_audit_log",
            audit,
        )

        maintenance = (
            maintenance_service.schedule_maintenance(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(),
            )
        )

        maintenance_service.cancel_maintenance(
            maintenance_id=maintenance.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
            data={
                "reason":
                    "Regression test"
            },
        )

        old_value = (
            audit.call_args.kwargs[
                "old_value"
            ]
        )

        assert (
            old_value["maintenance_status"]
            == MaintenanceStatus.SCHEDULED.value
        )


class TestGetAndListMaintenance:
    def test_get_maintenance_is_tenant_scoped(
        self,
        asset,
        clinic,
        user,
        make_clinic,
        monkeypatch,
    ):
        maintenance = _schedule(
            asset=asset,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        result = (
            maintenance_service.get_asset_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=clinic.id,
            )
        )

        assert result.id == maintenance.id

        other_clinic = make_clinic(
            name="Other Get Maintenance"
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset maintenance "
                f"{maintenance.id} not found"
            ),
        ):
            maintenance_service.get_asset_maintenance(
                maintenance_id=maintenance.id,
                clinic_id=other_clinic.id,
            )

    def test_lists_maintenance_with_filters(
        self,
        clinic,
        user,
        make_asset,
        monkeypatch,
    ):
        asset_a = make_asset(
            clinic,
            asset_tag="AST-MAINT-LIST-A",
        )

        asset_b = make_asset(
            clinic,
            asset_tag="AST-MAINT-LIST-B",
        )

        first = _schedule(
            asset=asset_a,
            clinic=clinic,
            user=user,
            monkeypatch=monkeypatch,
        )

        second = (
            maintenance_service.schedule_maintenance(
                asset_id=asset_b.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=_schedule_data(
                    scheduled_date=date(
                        2026,
                        9,
                        25,
                    ),
                    description="Second maintenance",
                ),
            )
        )

        maintenance_service.start_maintenance(
            maintenance_id=second.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )

        all_result = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query=AssetMaintenanceListQuerySchema(
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert all_result["total"] == 2

        by_asset = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query={
                    "asset_id": asset_a.id
                },
            )
        )

        assert by_asset["total"] == 1
        assert (
            by_asset["items"][0].id
            == first.id
        )

        by_status = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query={
                    "status":
                        MaintenanceStatus.IN_PROGRESS
                },
            )
        )

        assert by_status["total"] == 1
        assert (
            by_status["items"][0].id
            == second.id
        )

        by_date = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query={
                    "scheduled_from": date(
                        2026,
                        9,
                        24,
                    ),
                    "scheduled_to": date(
                        2026,
                        9,
                        26,
                    ),
                },
            )
        )

        assert by_date["total"] == 1
        assert (
            by_date["items"][0].id
            == second.id
        )

        by_performer = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query={
                    "performed_by_user_id":
                        user.id
                },
            )
        )

        assert by_performer["total"] == 1
        assert (
            by_performer["items"][0].id
            == second.id
        )

        page_result = (
            maintenance_service.list_asset_maintenance(
                clinic_id=clinic.id,
                query={
                    "page": 1,
                    "per_page": 1,
                },
            )
        )

        assert page_result["total"] == 2
        assert page_result["pages"] == 2
        assert page_result["has_next"] is True
        assert page_result["has_prev"] is False

    def test_requires_active_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(
            ValidationError,
            match=(
                f"Clinic {suspended_clinic.id} "
                "is not active"
            ),
        ):
            maintenance_service.list_asset_maintenance(
                clinic_id=suspended_clinic.id,
            )