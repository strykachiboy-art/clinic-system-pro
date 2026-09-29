from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.role_enums import Role
from pydantic import ValidationError as PydanticValidationError

from app.core.emergency_access.schemas.emergency_access_schema import (
    EmergencyAccessDecisionSchema,
    EmergencyAccessRequestSchema,
    EmergencyAccessRevokeSchema,
)
from app.core.enums.hie_enums import HIEPurposeOfUse
from app.modules.access_control.schemas.access_control_schema import (
    AccessControlClinicTransferSchema,
    AccessControlRoleUpdateSchema,
    AccessControlStatusUpdateSchema,
    AccessControlUserListQuerySchema,
)
from app.modules.hie.schemas.hie_schema import (
    HIEClinicalDataQuerySchema,
    HIEPatientQuerySchema,
    HIESubmissionQuerySchema,
)


class TestAccessControlValidationAbuse:
    @pytest.mark.parametrize(
        "value",
        [
            1,
            0,
            "true",
            "false",
            "1",
            "0",
            None,
        ],
    )
    def test_status_update_rejects_boolean_type_confusion(
        self,
        value,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlStatusUpdateSchema(
                is_active=value,
            )

    def test_status_update_rejects_unknown_security_field(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlStatusUpdateSchema(
                is_active=True,
                actor_id=999999,
            )

    @pytest.mark.parametrize(
        "value",
        [
            True,
            False,
            0,
            -1,
            "1",
            "999",
            None,
        ],
    )
    def test_clinic_transfer_rejects_invalid_id_types(
        self,
        value,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlClinicTransferSchema(
                destination_clinic_id=value,
            )

    def test_clinic_transfer_rejects_unknown_identity_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlClinicTransferSchema(
                destination_clinic_id=2,
                actor_id=999999,
                clinic_id=999999,
                user_id=999999,
            )

    @pytest.mark.parametrize(
        "page",
        [
            True,
            False,
            0,
            -1,
            "1",
            1.5,
        ],
    )
    def test_user_list_rejects_invalid_page_values(
        self,
        page,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlUserListQuerySchema(
                page=page,
            )

    @pytest.mark.parametrize(
        "per_page",
        [
            True,
            False,
            0,
            -1,
            501,
            "50",
            50.5,
        ],
    )
    def test_user_list_rejects_invalid_per_page_values(
        self,
        per_page,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlUserListQuerySchema(
                per_page=per_page,
            )

    def test_role_update_rejects_client_authorization_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            AccessControlRoleUpdateSchema(
                role="doctor",
                actor_id=999999,
                clinic_id=999999,
            )


class TestHIEValidationAbuse:
    def test_patient_query_rejects_client_supplied_authorization_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIEPatientQuerySchema(
                patient_identifier="REMOTE-123",
                purpose_of_use=HIEPurposeOfUse.TREATMENT,
                clinic_id=999999,
                requesting_user_id=999999,
            )

    @pytest.mark.parametrize(
        "integration_id",
        [
            True,
            False,
            0,
            -1,
            "1",
            1.5,
        ],
    )
    def test_patient_query_rejects_invalid_integration_id(
        self,
        integration_id,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIEPatientQuerySchema(
                patient_identifier="REMOTE-123",
                purpose_of_use=HIEPurposeOfUse.TREATMENT,
                integration_id=integration_id,
            )

    @pytest.mark.parametrize(
        "patient_identifier",
        [
            "",
            "   ",
            None,
            123,
            True,
        ],
    )
    def test_patient_query_rejects_invalid_patient_identifier(
        self,
        patient_identifier,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIEPatientQuerySchema(
                patient_identifier=patient_identifier,
                purpose_of_use=HIEPurposeOfUse.TREATMENT,
            )

    def test_clinical_query_rejects_non_object_filters(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIEClinicalDataQuerySchema(
                patient_identifier="REMOTE-123",
                purpose_of_use=HIEPurposeOfUse.TREATMENT,
                filters=["resource_type", "Medication"],
            )

    def test_clinical_query_rejects_client_identity_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIEClinicalDataQuerySchema(
                patient_identifier="REMOTE-123",
                purpose_of_use=HIEPurposeOfUse.TREATMENT,
                requesting_user_id=999999,
                clinic_id=999999,
            )

    @pytest.mark.parametrize(
        "value",
        [
            True,
            False,
            0,
            -1,
            "1",
            1.5,
        ],
    )
    def test_submission_query_rejects_invalid_pagination(
        self,
        value,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            HIESubmissionQuerySchema(
                page=value,
            )

        with pytest.raises(
            PydanticValidationError,
        ):
            HIESubmissionQuerySchema(
                per_page=value,
            )


class TestEmergencyAccessValidationAbuse:
    @pytest.mark.parametrize(
        "patient_id",
        [
            True,
            False,
            0,
            -1,
            "1",
            1.5,
            None,
        ],
    )
    def test_request_rejects_invalid_patient_id(
        self,
        patient_id,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessRequestSchema(
                patient_id=patient_id,
                reason="Emergency treatment",
                purpose="Emergency care",
                scope=["patient:read"],
            )

    def test_request_rejects_client_authorization_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessRequestSchema(
                patient_id=1,
                reason="Emergency treatment",
                purpose="Emergency care",
                scope=["patient:read"],
                actor_id=999999,
                clinic_id=999999,
                requester_user_id=999999,
            )

    def test_request_rejects_more_than_50_scope_entries(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessRequestSchema(
                patient_id=1,
                reason="Emergency treatment",
                purpose="Emergency care",
                scope=["patient:read"] * 51,
            )

    @pytest.mark.parametrize(
        "duration_minutes",
        [
            True,
            False,
            0,
            -1,
            61,
            "30",
            30.5,
            None,
        ],
    )
    def test_decision_rejects_invalid_duration_values(
        self,
        duration_minutes,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessDecisionSchema(
                duration_minutes=duration_minutes,
            )

    def test_decision_rejects_unknown_security_fields(
        self,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessDecisionSchema(
                duration_minutes=30,
                reviewer_id=999999,
                requester_id=999999,
            )

    @pytest.mark.parametrize(
        "reason",
        [
            "",
            "   ",
            123,
            True,
            "x" * 501,
            None,
        ],
    )
    def test_revoke_rejects_invalid_reason_values(
        self,
        reason,
    ):
        with pytest.raises(
            PydanticValidationError,
        ):
            EmergencyAccessRevokeSchema(
                reason=reason,
            )


class TestSecurityBoundaryValidationOrdering:
    def test_access_control_route_validates_payload_before_service(
        self,
        client,
        auth_headers_for,
        make_user,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role="super_admin",
            email="validation-super-admin@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            "app.modules.access_control.routes.access_control_routes.change_user_role",
            service,
        )

        response = client.patch(
            "/api/v1/access-control/users/1/role",
            json={
                "role": "doctor",
                "actor_id": 999999,
                "clinic_id": 999999,
                "user_id": 999999,
            },
            headers=auth_headers_for(super_admin),
        )

        assert response.status_code == 422
        service.assert_not_called()

    def test_emergency_request_validates_payload_before_service(
        self,
        client,
        auth_headers_for,
        make_staff,
        clinic,
        monkeypatch,
    ):
        staff = make_staff(
            clinic,
            role=Role.DOCTOR,
        )

        service = Mock()

        monkeypatch.setattr(
            "app.core.emergency_access.routes.emergency_access_routes.request_emergency_access",
            service,
        )

        response = client.post(
            "/api/v1/emergency-access/requests",
            json={
                "patient_id": True,
                "reason": "Emergency treatment",
                "purpose": "Emergency care",
                "scope": ["patient:read"],
                "actor_id": 999999,
            },
            headers=auth_headers_for(
                staff.user,
            ),
        )

        assert response.status_code == 422
        service.assert_not_called()