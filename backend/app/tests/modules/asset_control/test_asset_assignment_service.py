from __future__ import annotations

from unittest.mock import Mock

import pytest

import app.modules.asset_control.services.asset_assignment_service as assignment_service
from app.core.enums.asset_enums import (
    AssetHistoryEventType,
    AssetStatus,
)
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.asset_control.models.asset_assignment_model import (
    AssetAssignment,
)
from app.modules.asset_control.models.asset_history_model import (
    AssetHistory,
)
from app.modules.asset_control.models.asset_model import Asset
from app.modules.asset_control.schemas.asset_assignment_schema import (
    AssetAssignmentListQuerySchema,
    AssetAssignmentCreateSchema,
)


class TestAssignAsset:
    def test_assigns_asset_and_records_history(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        audit = Mock()

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            audit,
        )

        assignment = (
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id,
                    "notes": "  Handed to ICU nurse  ",
                },
            )
        )

        assert assignment.id is not None
        assert (
            assignment.clinic_id
            == clinic.id
        )
        assert (
            assignment.asset_id
            == asset.id
        )
        assert (
            assignment.staff_id
            == staff.id
        )
        assert (
            assignment.assigned_by_user_id
            == user.id
        )
        assert assignment.returned_at is None
        assert (
            assignment.notes
            == "  Handed to ICU nurse  "
        )

        refreshed = db.session.get(
            Asset,
            asset.id,
        )

        assert (
            refreshed.assigned_to_id
            == staff.id
        )
        assert (
            refreshed.status
            == AssetStatus.ASSIGNED
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.ASSIGNED,
            )
        ).scalar_one()

        assert (
            history.previous_status
            == AssetStatus.ACTIVE
        )

        assert (
            history.new_status
            == AssetStatus.ASSIGNED
        )

        assert (
            history.previous_assigned_to_id
            is None
        )

        assert (
            history.new_assigned_to_id
            == staff.id
        )

        assert (
            history.event_metadata[
                "assignment_id"
            ]
            == assignment.id
        )

        audit.assert_called_once()

    def test_accepts_schema_input(
        self,
        make_asset,
        clinic,
        user,
        make_staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        staff_obj = make_staff(clinic)
        asset_obj = make_asset(
            clinic,
            asset_tag="AST-ASG-SCHEMA",
        )

        schema = AssetAssignmentCreateSchema(
            staff_id=staff_obj.id,
            notes="schema input",
        )

        result = (
            assignment_service.assign_asset(
                asset_id=asset_obj.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data=schema,
            )
        )

        assert (
            result.staff_id
            == staff_obj.id
        )

        assert (
            result.notes
            == "schema input"
        )

    def test_rejects_unavailable_states(
        self,
        db,
        make_asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        db.session.commit()

        candidates = [
            (
                AssetStatus.RETIRED,
                False,
                "is no longer assignable",
            ),
            (
                AssetStatus.DISPOSED,
                False,
                "is no longer assignable",
            ),
            (
                AssetStatus.LOST,
                True,
                "is not available for assignment",
            ),
            (
                AssetStatus.UNDER_MAINTENANCE,
                True,
                "is not available for assignment",
            ),
            (
                AssetStatus.OUT_OF_SERVICE,
                True,
                "is not available for assignment",
            ),
        ]

        for (
            index,
            (status, active, message),
        ) in enumerate(candidates):
            candidate = make_asset(
                clinic,
                asset_tag=(
                    f"AST-ASG-STATE-{index}"
                ),
                status=status,
                is_active=active,
            )

            with pytest.raises(
                ConflictError,
                match=(
                    rf"Asset {candidate.id} .*"
                    rf"{message}"
                ),
            ):
                assignment_service.assign_asset(
                    asset_id=candidate.id,
                    clinic_id=clinic.id,
                    actor_user_id=user.id,
                    data={
                        "staff_id": staff.id
                    },
                )

    def test_rejects_inactive_asset(
        self,
        make_asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        candidate = make_asset(
            clinic,
            asset_tag="AST-INACTIVE",
            is_active=False,
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {candidate.id} "
                "is inactive"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=candidate.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )

    def test_rejects_already_assigned_asset(
        self,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        asset.assigned_to_id = staff.id

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {asset.id} "
                "is already assigned"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )

    def test_rejects_existing_active_assignment_record(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        existing = AssetAssignment(
            clinic_id=clinic.id,
            asset_id=asset.id,
            staff_id=staff.id,
            assigned_by_user_id=user.id,
        )

        db.session.add(existing)
        db.session.flush()

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {asset.id} "
                "already has an active assignment"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )

    def test_rejects_missing_staff(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match="Staff 999999 not found",
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": 999999
                },
            )

    def test_rejects_inactive_staff(
        self,
        asset,
        clinic,
        user,
        make_staff,
        monkeypatch,
    ):
        inactive = make_staff(
            clinic,
            status=StaffStatus.SUSPENDED,
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ValidationError,
            match=(
                f"Staff {inactive.id} "
                "is not active"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": inactive.id
                },
            )

    def test_rejects_staff_from_other_clinic(
        self,
        asset,
        clinic,
        make_clinic,
        make_staff,
        user,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Assignment Clinic"
        )

        other_staff = make_staff(
            other_clinic
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Staff {other_staff.id} "
                "not found"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": other_staff.id
                },
            )

    def test_rejects_cross_clinic_actor(
        self,
        asset,
        clinic,
        make_clinic,
        make_user,
        staff,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Actor Clinic"
        )

        other_user = make_user(
            other_clinic
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=(
                "Authenticated user not found"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=other_user.id,
                data={
                    "staff_id": staff.id
                },
            )

    def test_rejects_cross_clinic_asset(
        self,
        make_asset,
        clinic,
        make_clinic,
        user,
        staff,
        monkeypatch,
    ):
        other_clinic = make_clinic(
            name="Other Asset Clinic"
        )

        other_asset = make_asset(
            other_clinic,
            asset_tag="AST-OTHER-001",
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset {other_asset.id} "
                "not found"
            ),
        ):
            assignment_service.assign_asset(
                asset_id=other_asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )

    def test_rolls_back_when_history_fails(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "record_asset_history",
            Mock(
                side_effect=RuntimeError(
                    "history failed"
                )
            ),
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        db.session.commit()

        with pytest.raises(
            RuntimeError,
            match="history failed",
        ):
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )

        db.session.expire_all()

        persisted_asset = db.session.get(
            Asset,
            asset.id,
        )

        persisted_assignment = (
            db.session.execute(
                db.select(
                    AssetAssignment
                ).where(
                    AssetAssignment.asset_id
                    == asset.id
                )
            )
            .scalar_one_or_none()
        )

        assert (
            persisted_asset.assigned_to_id
            is None
        )

        assert (
            persisted_asset.status
            == AssetStatus.ACTIVE
        )

        assert (
            persisted_assignment
            is None
        )


class TestReturnAsset:
    def test_returns_active_assignment(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        assignment = (
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id,
                    "notes": "Initial",
                },
            )
        )

        result = (
            assignment_service.return_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "notes":
                        "Returned to equipment room"
                },
            )
        )

        assert result.id == assignment.id
        assert result.returned_at is not None
        assert (
            result.returned_by_user_id
            == user.id
        )

        assert (
            result.notes
            == "Returned to equipment room"
        )

        refreshed_asset = db.session.get(
            Asset,
            asset.id,
        )

        assert (
            refreshed_asset.assigned_to_id
            is None
        )

        assert (
            refreshed_asset.status
            == AssetStatus.ACTIVE
        )

        history = db.session.execute(
            db.select(AssetHistory).where(
                AssetHistory.asset_id == asset.id,
                AssetHistory.event_type
                == AssetHistoryEventType.UNASSIGNED,
            )
        ).scalar_one()

        assert (
            history.previous_assigned_to_id
            == staff.id
        )

        assert (
            history.new_assigned_to_id
            is None
        )

        assert (
            history.previous_status
            == AssetStatus.ASSIGNED
        )

        assert (
            history.new_status
            == AssetStatus.ACTIVE
        )

    def test_keeps_existing_notes_when_return_notes_missing(
        self,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        assignment = (
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id,
                    "notes": "Keep this",
                },
            )
        )

        result = (
            assignment_service.return_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )
        )

        assert (
            result.notes
            == "Keep this"
        )

    def test_rejects_return_without_active_assignment(
        self,
        asset,
        clinic,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"No active assignment "
                f"found for asset {asset.id}"
            ),
        ):
            assignment_service.return_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_rejects_inconsistent_state(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        make_staff,
        monkeypatch,
    ):
        assignment = AssetAssignment(
            clinic_id=clinic.id,
            asset_id=asset.id,
            staff_id=staff.id,
            assigned_by_user_id=user.id,
        )

        db.session.add(assignment)
        db.session.flush()

        other_staff = make_staff(clinic)

        asset.assigned_to_id = (
            other_staff.id
        )

        asset.status = (
            AssetStatus.ASSIGNED
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        with pytest.raises(
            ConflictError,
            match=(
                f"Asset {asset.id} "
                "assignment state is inconsistent"
            ),
        ):
            assignment_service.return_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

    def test_hides_return_target_across_clinics(
        self,
        make_asset,
        make_clinic,
        make_user,
        make_staff,
        monkeypatch,
    ):
        clinic_a = make_clinic(
            name="Assignment A"
        )

        clinic_b = make_clinic(
            name="Assignment B"
        )

        user_b = make_user(clinic_b)
        staff_b = make_staff(clinic_b)

        asset_b = make_asset(
            clinic_b,
            asset_tag="AST-B-RETURN",
        )

        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        assignment_service.assign_asset(
            asset_id=asset_b.id,
            clinic_id=clinic_b.id,
            actor_user_id=user_b.id,
            data={
                "staff_id": staff_b.id
            },
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset {asset_b.id} "
                "not found"
            ),
        ):
            assignment_service.return_asset(
                asset_id=asset_b.id,
                clinic_id=clinic_a.id,
                actor_user_id=make_user(
                    clinic_a
                ).id,
            )

    def test_rolls_back_return_when_history_fails(
        self,
        db,
        asset,
        clinic,
        user,
        staff,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        assignment = (
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )
        )

        monkeypatch.setattr(
            assignment_service,
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
            assignment_service.return_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
            )

        db.session.expire_all()

        persisted_asset = db.session.get(
            Asset,
            asset.id,
        )

        persisted_assignment = (
            db.session.get(
                AssetAssignment,
                assignment.id,
            )
        )

        assert (
            persisted_asset.assigned_to_id
            == staff.id
        )

        assert (
            persisted_asset.status
            == AssetStatus.ASSIGNED
        )

        assert (
            persisted_assignment.returned_at
            is None
        )

        assert (
            persisted_assignment
            .returned_by_user_id
            is None
        )


class TestGetAndListAssetAssignments:
    def test_get_assignment_is_tenant_scoped(
        self,
        clinic,
        user,
        staff,
        asset,
        make_clinic,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        assignment = (
            assignment_service.assign_asset(
                asset_id=asset.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff.id
                },
            )
        )

        result = (
            assignment_service.get_asset_assignment(
                assignment_id=assignment.id,
                clinic_id=clinic.id,
            )
        )

        assert result.id == assignment.id

        other_clinic = make_clinic(
            name="Other Get Assignment"
        )

        with pytest.raises(
            NotFoundError,
            match=(
                f"Asset assignment "
                f"{assignment.id} not found"
            ),
        ):
            assignment_service.get_asset_assignment(
                assignment_id=assignment.id,
                clinic_id=other_clinic.id,
            )

    def test_lists_assignments_with_filters(
        self,
        clinic,
        user,
        make_staff,
        make_asset,
        monkeypatch,
    ):
        monkeypatch.setattr(
            assignment_service,
            "create_audit_log",
            Mock(),
        )

        staff_a = make_staff(clinic)
        staff_b = make_staff(clinic)

        asset_a = make_asset(
            clinic,
            asset_tag="AST-LIST-ASG-A",
        )

        asset_b = make_asset(
            clinic,
            asset_tag="AST-LIST-ASG-B",
        )

        first = (
            assignment_service.assign_asset(
                asset_id=asset_a.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff_a.id
                },
            )
        )

        second = (
            assignment_service.assign_asset(
                asset_id=asset_b.id,
                clinic_id=clinic.id,
                actor_user_id=user.id,
                data={
                    "staff_id": staff_b.id
                },
            )
        )

        assignment_service.return_asset(
            asset_id=asset_a.id,
            clinic_id=clinic.id,
            actor_user_id=user.id,
        )

        all_result = (
            assignment_service.list_asset_assignments(
                clinic_id=clinic.id,
                query=AssetAssignmentListQuerySchema(
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert all_result["total"] == 2

        active_result = (
            assignment_service.list_asset_assignments(
                clinic_id=clinic.id,
                query=AssetAssignmentListQuerySchema(
                    active_only=True,
                    page=1,
                    per_page=10,
                ),
            )
        )

        assert active_result["total"] == 1
        assert (
            active_result["items"][0].id
            == second.id
        )

        by_staff = (
            assignment_service.list_asset_assignments(
                clinic_id=clinic.id,
                query={
                    "staff_id": staff_a.id
                },
            )
        )

        assert by_staff["total"] == 1
        assert (
            by_staff["items"][0].id
            == first.id
        )

        by_asset = (
            assignment_service.list_asset_assignments(
                clinic_id=clinic.id,
                query={
                    "asset_id": asset_b.id
                },
            )
        )

        assert by_asset["total"] == 1
        assert (
            by_asset["items"][0].id
            == second.id
        )

        paginated = (
            assignment_service.list_asset_assignments(
                clinic_id=clinic.id,
                query={
                    "page": 1,
                    "per_page": 1,
                },
            )
        )

        assert paginated["total"] == 2
        assert paginated["pages"] == 2
        assert paginated["has_next"] is True
        assert paginated["has_prev"] is False

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
            assignment_service.list_asset_assignments(
                clinic_id=suspended_clinic.id,
            )