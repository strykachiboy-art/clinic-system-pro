from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums.asset_enums import (
    AssetCondition,
    AssetHistoryEventType,
    AssetStatus,
)
from app.core.exceptions import NotFoundError
from app.modules.asset_control.models.asset_history_model import (
    AssetHistory,
)
from app.modules.asset_control.schemas.asset_history_schema import (
    AssetHistoryListQuerySchema,
)
from app.modules.asset_control.services import (
    asset_history_service,
)


class TestRecordAssetHistory:
    def test_records_full_history_snapshot(
        self,
        db,
        clinic,
        user,
        asset,
    ):
        event_at = datetime(
            2026,
            9,
            18,
            10,
            15,
            tzinfo=timezone.utc,
        )

        history = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.UPDATED,
                actor_user_id=user.id,
                previous_status=AssetStatus.ACTIVE,
                new_status=AssetStatus.ASSIGNED,
                previous_condition=AssetCondition.GOOD,
                new_condition=AssetCondition.GOOD,
                previous_assigned_to_id=None,
                new_assigned_to_id=11,
                previous_location="Ward",
                new_location="ICU",
                reason="Moved",
                notes="Test event",
                event_metadata={
                    "source": "unit-test"
                },
                event_at=event_at,
            )
        )

        assert history.id is not None
        assert history.clinic_id == clinic.id
        assert history.asset_id == asset.id
        assert (
            history.event_type
            == AssetHistoryEventType.UPDATED
        )
        assert history.actor_user_id == user.id
        assert (
            history.previous_status
            == AssetStatus.ACTIVE
        )
        assert (
            history.new_status
            == AssetStatus.ASSIGNED
        )
        assert (
            history.previous_condition
            == AssetCondition.GOOD
        )
        assert (
            history.new_condition
            == AssetCondition.GOOD
        )
        assert (
            history.previous_assigned_to_id
            is None
        )
        assert (
            history.new_assigned_to_id
            == 11
        )
        assert (
            history.previous_location
            == "Ward"
        )
        assert history.new_location == "ICU"
        assert history.reason == "Moved"
        assert history.notes == "Test event"
        assert (
            history.event_metadata
            == {"source": "unit-test"}
        )

        persisted = db.session.get(
            AssetHistory,
            history.id,
        )

        assert persisted is not None
        assert persisted.id == history.id

    def test_generates_event_time_when_not_supplied(
        self,
        clinic,
        asset,
    ):
        history = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.CREATED,
            )
        )

        assert history.event_at is not None


class TestGetAssetHistory:
    def test_returns_history_from_same_clinic(
        self,
        clinic,
        asset,
    ):
        history = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.CREATED,
            )
        )

        result = (
            asset_history_service.get_asset_history(
                history_id=history.id,
                clinic_id=clinic.id,
            )
        )

        assert result.id == history.id

    def test_hides_history_from_other_clinic(
        self,
        clinic,
        make_clinic,
        asset,
    ):
        other_clinic = make_clinic(
            name="Other History Clinic"
        )

        history = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.CREATED,
            )
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset history "
                f"{history.id} not found"
            ),
        ):
            asset_history_service.get_asset_history(
                history_id=history.id,
                clinic_id=other_clinic.id,
            )

    def test_missing_history_raises_not_found(
        self,
        clinic,
    ):
        with pytest.raises(
            NotFoundError,
            match="Asset history 999999 not found",
        ):
            asset_history_service.get_asset_history(
                history_id=999999,
                clinic_id=clinic.id,
            )


class TestListAssetHistory:
    def test_lists_in_descending_order(
        self,
        clinic,
        asset,
    ):
        first = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.CREATED,
                event_at=datetime(
                    2026,
                    9,
                    18,
                    9,
                    0,
                ),
            )
        )

        second = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.UPDATED,
                event_at=datetime(
                    2026,
                    9,
                    18,
                    10,
                    0,
                ),
            )
        )

        third = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.UPDATED,
                event_at=datetime(
                    2026,
                    9,
                    18,
                    10,
                    0,
                ),
            )
        )

        result = (
            asset_history_service.list_asset_history(
                clinic_id=clinic.id,
                query=AssetHistoryListQuerySchema(
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert [
            item.id
            for item in result["items"]
        ] == [
            third.id,
            second.id,
            first.id,
        ]

    def test_filters_by_asset_event_actor_and_date_window(
        self,
        clinic,
        asset,
        make_asset,
        user,
        make_user,
    ):
        other_asset = make_asset(
            clinic,
            asset_tag="AST-HISTORY-OTHER",
        )

        other_user = make_user(
            clinic
        )

        matching = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.LOCATION_CHANGED,
                actor_user_id=user.id,
                event_at=datetime(
                    2026,
                    9,
                    18,
                    10,
                    0,
                ),
            )
        )

        asset_history_service.record_asset_history(
            clinic_id=clinic.id,
            asset_id=asset.id,
            event_type=AssetHistoryEventType.UPDATED,
            actor_user_id=other_user.id,
            event_at=datetime(
                2026,
                9,
                18,
                11,
                0,
            ),
        )

        asset_history_service.record_asset_history(
            clinic_id=clinic.id,
            asset_id=other_asset.id,
            event_type=AssetHistoryEventType.LOCATION_CHANGED,
            actor_user_id=user.id,
            event_at=datetime(
                2026,
                9,
                18,
                10,
                0,
            ),
        )

        result = (
            asset_history_service.list_asset_history(
                clinic_id=clinic.id,
                query=AssetHistoryListQuerySchema(
                    asset_id=asset.id,
                    event_type=(
                        AssetHistoryEventType.LOCATION_CHANGED
                    ),
                    actor_user_id=user.id,
                    event_from=datetime(
                        2026,
                        9,
                        18,
                        9,
                        59,
                    ),
                    event_to=datetime(
                        2026,
                        9,
                        18,
                        10,
                        1,
                    ),
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert result["total"] == 1
        assert (
            result["items"][0].id
            == matching.id
        )

    def test_paginates_results(
        self,
        clinic,
        asset,
    ):
        for index in range(5):
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.UPDATED,
                event_at=datetime(
                    2026,
                    9,
                    18,
                    8,
                    index,
                ),
            )

        result = (
            asset_history_service.list_asset_history(
                clinic_id=clinic.id,
                query=AssetHistoryListQuerySchema(
                    page=2,
                    per_page=2,
                ),
            )
        )

        assert result["page"] == 2
        assert result["per_page"] == 2
        assert result["total"] == 5
        assert result["pages"] == 3
        assert result["has_next"] is True
        assert result["has_prev"] is True
        assert len(result["items"]) == 2

    def test_isolates_clinic_history(
        self,
        clinic,
        make_clinic,
        make_asset,
    ):
        other_clinic = make_clinic(
            name="Other Tenant History"
        )

        other_asset = make_asset(
            other_clinic,
            asset_tag="AST-OTHER-HISTORY",
        )

        other_history = (
            asset_history_service.record_asset_history(
                clinic_id=other_clinic.id,
                asset_id=other_asset.id,
                event_type=AssetHistoryEventType.CREATED,
            )
        )

        local_history = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=make_asset(
                    clinic,
                    asset_tag="AST-LOCAL-HISTORY",
                ).id,
                event_type=AssetHistoryEventType.CREATED,
            )
        )

        result = (
            asset_history_service.list_asset_history(
                clinic_id=other_clinic.id,
                query=AssetHistoryListQuerySchema(
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert result["total"] == 1
        assert (
            result["items"][0].id
            == other_history.id
        )

        local_result = (
            asset_history_service.list_asset_history(
                clinic_id=clinic.id,
                query=AssetHistoryListQuerySchema(
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert local_result["total"] == 1
        assert (
            local_result["items"][0].id
            == local_history.id
        )


class TestGetLatestMaintenanceStart:
    def test_returns_latest_maintenance_start(
        self,
        clinic,
        asset,
    ):
        older = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.MAINTENANCE_STARTED,
                event_metadata={
                    "previous_asset_status": "active"
                },
                event_at=datetime(
                    2026,
                    9,
                    18,
                    8,
                    0,
                ),
            )
        )

        latest = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.MAINTENANCE_STARTED,
                event_metadata={
                    "previous_asset_status": "assigned"
                },
                event_at=datetime(
                    2026,
                    9,
                    18,
                    9,
                    0,
                ),
            )
        )

        asset_history_service.record_asset_history(
            clinic_id=clinic.id,
            asset_id=asset.id,
            event_type=AssetHistoryEventType.UPDATED,
            event_metadata={
                "other": True
            },
            event_at=datetime(
                2026,
                9,
                18,
                10,
                0,
            ),
        )

        result = (
            asset_history_service.get_latest_maintenance_start(
                clinic_id=clinic.id,
                asset_id=asset.id,
            )
        )

        assert result is not None
        assert result.id == latest.id
        assert result.id != older.id

    def test_uses_id_as_tie_breaker(
        self,
        clinic,
        asset,
    ):
        event_at = datetime(
            2026,
            9,
            18,
            12,
            0,
        )

        first = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.MAINTENANCE_STARTED,
                event_at=event_at,
            )
        )

        second = (
            asset_history_service.record_asset_history(
                clinic_id=clinic.id,
                asset_id=asset.id,
                event_type=AssetHistoryEventType.MAINTENANCE_STARTED,
                event_at=event_at,
            )
        )

        result = (
            asset_history_service.get_latest_maintenance_start(
                clinic_id=clinic.id,
                asset_id=asset.id,
            )
        )

        assert result.id == second.id
        assert result.id > first.id

    def test_returns_none_when_missing(
        self,
        clinic,
        asset,
    ):
        assert (
            asset_history_service
            .get_latest_maintenance_start(
                clinic_id=clinic.id,
                asset_id=asset.id,
            )
            is None
        )