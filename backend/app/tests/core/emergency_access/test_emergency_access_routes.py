from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.emergency_access.routes import (
    emergency_access_routes as emergency_access_route,
)
from app.core.enums.emergency_access_enums import (
    EmergencyAccessStatus,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


REQUEST_ENDPOINT = "/api/v1/emergency-access/requests"


DEFAULT_REQUEST_PAYLOAD = {
    "patient_id": 1,
    "reason": "Immediate emergency treatment required.",
    "purpose": "Emergency clinical care.",
    "scope": [
        "patient:read",
    ],
}


DEFAULT_DECISION_PAYLOAD = {
    "duration_minutes": 30,
    "review_notes": "Approved for emergency treatment.",
}


DEFAULT_REVOKE_PAYLOAD = {
    "reason": "Emergency treatment completed.",
}


class TestRequestEmergencyAccessRoute:
    def test_requires_authentication(
        self,
        client,
    ):
        response = client.post(
            REQUEST_ENDPOINT,
            json=DEFAULT_REQUEST_PAYLOAD,
        )

        assert response.status_code == 401

    def test_rejects_forbidden_role(
        self,
        client,
        auth_headers_for,
        emergency_patient_user,
    ):
        headers = auth_headers_for(
            emergency_patient_user,
            role=Role.PATIENT,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json=DEFAULT_REQUEST_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 403

    def test_rejects_inactive_authenticated_user(
        self,
        client,
        auth_headers_for,
        emergency_staff,
    ):
        emergency_staff.user.is_active = False

        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json=DEFAULT_REQUEST_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 401

    def test_rejects_non_active_staff(
        self,
        client,
        auth_headers_for,
        make_emergency_staff,
        clinic,
        emergency_patient,
    ):
        staff = make_emergency_staff(
            clinic,
            role=Role.DOCTOR,
            status=StaffStatus.SUSPENDED,
        )

        headers = auth_headers_for(
            staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json={
                **DEFAULT_REQUEST_PAYLOAD,
                "patient_id": emergency_patient.id,
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_creates_request(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_patient,
        emergency_requested_grant,
        monkeypatch,
    ):
        called = {}

        def fake_request_emergency_access(**kwargs):
            called.update(kwargs)
            return emergency_requested_grant

        monkeypatch.setattr(
            emergency_access_route,
            "request_emergency_access",
            fake_request_emergency_access,
        )

        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json={
                "patient_id": emergency_patient.id,
                "reason": "Immediate emergency treatment required.",
                "purpose": "Emergency clinical care.",
                "scope": [
                    "patient:read",
                    "consultation:123:read",
                ],
            },
            headers=headers,
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == emergency_requested_grant.id
        assert (
            body["data"]["clinic_id"]
            == emergency_requested_grant.clinic_id
        )
        assert (
            body["data"]["patient_id"]
            == emergency_requested_grant.patient_id
        )
        assert (
            body["data"]["requester_user_id"]
            == emergency_requested_grant.requester_user_id
        )
        assert (
            body["data"]["status"]
            == EmergencyAccessStatus.REQUESTED.value
        )

        assert called == {
            "actor_id": emergency_staff.user.id,
            "patient_id": emergency_patient.id,
            "reason": (
                "Immediate emergency treatment required."
            ),
            "purpose": "Emergency clinical care.",
            "scope": [
                "patient:read",
                "consultation:123:read",
            ],
        }

    def test_uses_authenticated_actor_and_rejects_client_actor_id(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_patient,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json={
                **DEFAULT_REQUEST_PAYLOAD,
                "patient_id": emergency_patient.id,
                "actor_id": 999999,
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_rejects_unknown_request_field(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_patient,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json={
                "patient_id": emergency_patient.id,
                "reason": "Emergency treatment.",
                "purpose": "Emergency care.",
                "scope": ["patient:read"],
                "unknown_field": "bad",
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_rejects_invalid_json_body(
        self,
        client,
        auth_headers_for,
        emergency_staff,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json=[
                "not",
                "an",
                "object",
            ],
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {
                "patient_id": "1",
                "reason": "Emergency treatment.",
                "purpose": "Emergency care.",
                "scope": ["patient:read"],
            },
            {
                "patient_id": True,
                "reason": "Emergency treatment.",
                "purpose": "Emergency care.",
                "scope": ["patient:read"],
            },
            {
                "patient_id": 1,
                "reason": "",
                "purpose": "Emergency care.",
                "scope": ["patient:read"],
            },
            {
                "patient_id": 1,
                "reason": "Emergency treatment.",
                "purpose": "",
                "scope": ["patient:read"],
            },
            {
                "patient_id": 1,
                "reason": "Emergency treatment.",
                "purpose": "Emergency care.",
                "scope": [],
            },
        ],
    )
    def test_rejects_invalid_request_payload(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        payload,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422

    def test_propagates_request_conflict_error(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_patient,
        monkeypatch,
    ):
        def fake_request_emergency_access(**kwargs):
            raise ConflictError(
                "An existing emergency access request is already active"
            )

        monkeypatch.setattr(
            emergency_access_route,
            "request_emergency_access",
            fake_request_emergency_access,
        )

        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.post(
            REQUEST_ENDPOINT,
            json={
                **DEFAULT_REQUEST_PAYLOAD,
                "patient_id": emergency_patient.id,
            },
            headers=headers,
        )

        assert response.status_code == 409

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == (
                "An existing emergency access request "
                "is already active"
            )
        )


class TestGetEmergencyAccessRoute:
    def test_requires_authentication(
        self,
        client,
        emergency_requested_grant,
    ):
        response = client.get(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}",
        )

        assert response.status_code == 401

    def test_rejects_forbidden_role(
        self,
        client,
        auth_headers_for,
        emergency_patient_user,
        emergency_requested_grant,
    ):
        headers = auth_headers_for(
            emergency_patient_user,
            role=Role.PATIENT,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}",
            headers=headers,
        )

        assert response.status_code == 403

    def test_gets_visible_grant(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_requested_grant,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == emergency_requested_grant.id
        assert (
            body["data"]["clinic_id"]
            == emergency_requested_grant.clinic_id
        )
        assert (
            body["data"]["patient_id"]
            == emergency_requested_grant.patient_id
        )
        assert (
            body["data"]["requester_user_id"]
            == emergency_requested_grant.requester_user_id
        )
        assert (
            body["data"]["requester_role"]
            == emergency_requested_grant.requester_role
        )
        assert (
            body["data"]["status"]
            == emergency_requested_grant.status.value
        )
        assert (
            body["data"]["requested_at"]
            is not None
        )

    def test_rejects_foreign_clinic_grant(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_requested_grant,
        emergency_other_clinic,
        emergency_other_staff,
        emergency_other_patient,
        make_emergency_grant,
    ):
        foreign_grant = make_emergency_grant(
            clinic=emergency_other_clinic,
            patient=emergency_other_patient,
            requester_user=emergency_other_staff.user,
            requester_role=Role.DOCTOR.value,
        )

        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/{foreign_grant.id}",
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["success"] is False
        assert (
            body["error"]
            == "Emergency access request not found"
        )

    def test_super_admin_can_view_foreign_clinic_grant(
        self,
        client,
        auth_headers_for,
        emergency_super_admin,
        emergency_other_clinic,
        emergency_other_staff,
        emergency_other_patient,
        make_emergency_grant,
    ):
        foreign_grant = make_emergency_grant(
            clinic=emergency_other_clinic,
            patient=emergency_other_patient,
            requester_user=emergency_other_staff.user,
            requester_role=Role.DOCTOR.value,
        )

        headers = auth_headers_for(
            emergency_super_admin,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/{foreign_grant.id}",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == foreign_grant.id
        assert (
            body["data"]["clinic_id"]
            == emergency_other_clinic.id
        )

    @pytest.mark.parametrize(
        "emergency_access_id,expected_status",
        [
            (0, 422),
            (-1, 404),
        ],
    )
    def test_rejects_invalid_emergency_access_id(
        self,
        client,
        auth_headers_for,
        emergency_staff,
        emergency_access_id,
        expected_status,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/{emergency_access_id}",
            headers=headers,
        )

        assert response.status_code == expected_status

    def test_returns_not_found_for_missing_grant(
        self,
        client,
        auth_headers_for,
        emergency_staff,
    ):
        headers = auth_headers_for(
            emergency_staff.user,
        )

        response = client.get(
            f"{REQUEST_ENDPOINT}/999999",
            headers=headers,
        )

        assert response.status_code == 404


class TestGrantEmergencyAccessRoute:
    def test_requires_authentication(
        self,
        client,
        emergency_requested_grant,
    ):
        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/grant",
            json=DEFAULT_DECISION_PAYLOAD,
        )

        assert response.status_code == 401

    def test_rejects_forbidden_role(
        self,
        client,
        auth_headers_for,
        emergency_patient_user,
        emergency_requested_grant,
    ):
        headers = auth_headers_for(
            emergency_patient_user,
            role=Role.PATIENT,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/grant",
            json=DEFAULT_DECISION_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 403

    def test_grants_request(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_requested_grant,
        emergency_active_grant,
        monkeypatch,
    ):
        called = {}

        def fake_grant_emergency_access(**kwargs):
            called.update(kwargs)
            return emergency_active_grant

        monkeypatch.setattr(
            emergency_access_route,
            "grant_emergency_access",
            fake_grant_emergency_access,
        )

        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/grant",
            json={
                "duration_minutes": 45,
                "review_notes": "Approved for emergency treatment.",
            },
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == emergency_active_grant.id
        assert (
            body["data"]["status"]
            == EmergencyAccessStatus.ACTIVE.value
        )

        assert called == {
            "emergency_access_id": emergency_requested_grant.id,
            "reviewer_id": emergency_reviewer.id,
            "duration_minutes": 45,
            "review_notes": "Approved for emergency treatment.",
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {
                "duration_minutes": 0,
            },
            {
                "duration_minutes": 61,
            },
            {
                "duration_minutes": "30",
            },
            {
                "duration_minutes": 30.5,
            },
            {
                "duration_minutes": 30,
                "unknown_field": "bad",
            },
        ],
    )
    def test_rejects_invalid_grant_payload(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_requested_grant,
        payload,
    ):
        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/grant",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422

    def test_propagates_grant_conflict_error(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_requested_grant,
        monkeypatch,
    ):
        def fake_grant_emergency_access(**kwargs):
            raise ConflictError(
                "Emergency access request cannot be granted from status 'active'"
            )

        monkeypatch.setattr(
            emergency_access_route,
            "grant_emergency_access",
            fake_grant_emergency_access,
        )

        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/grant",
            json=DEFAULT_DECISION_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 409


class TestDenyEmergencyAccessRoute:
    def test_requires_authentication(
        self,
        client,
        emergency_requested_grant,
    ):
        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/deny",
            json=DEFAULT_DECISION_PAYLOAD,
        )

        assert response.status_code == 401

    def test_rejects_forbidden_role(
        self,
        client,
        auth_headers_for,
        emergency_patient_user,
        emergency_requested_grant,
    ):
        headers = auth_headers_for(
            emergency_patient_user,
            role=Role.PATIENT,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/deny",
            json=DEFAULT_DECISION_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 403

    def test_denies_request(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_requested_grant,
        monkeypatch,
    ):
        emergency_requested_grant.status = (
            EmergencyAccessStatus.DENIED
        )
        emergency_requested_grant.reviewed_at = (
            datetime.now(timezone.utc)
        )
        emergency_requested_grant.reviewed_by_user_id = (
            emergency_reviewer.id
        )
        emergency_requested_grant.review_notes = (
            "Insufficient justification."
        )

        called = {}

        def fake_deny_emergency_access(**kwargs):
            called.update(kwargs)
            return emergency_requested_grant

        monkeypatch.setattr(
            emergency_access_route,
            "deny_emergency_access",
            fake_deny_emergency_access,
        )

        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/deny",
            json={
                "duration_minutes": 30,
                "review_notes": (
                    "Insufficient justification."
                ),
            },
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == (
            emergency_requested_grant.id
        )
        assert (
            body["data"]["status"]
            == EmergencyAccessStatus.DENIED.value
        )
        assert (
            body["data"]["reviewed_by_user_id"]
            == emergency_reviewer.id
        )
        assert (
            body["data"]["review_notes"]
            == "Insufficient justification."
        )

        assert called == {
            "emergency_access_id": (
                emergency_requested_grant.id
            ),
            "reviewer_id": emergency_reviewer.id,
            "review_notes": (
                "Insufficient justification."
            ),
        }

    def test_rejects_invalid_deny_payload(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_requested_grant,
    ):
        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_requested_grant.id}/deny",
            json={},
            headers=headers,
        )

        assert response.status_code == 422


class TestRevokeEmergencyAccessRoute:
    def test_requires_authentication(
        self,
        client,
        emergency_active_grant,
    ):
        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_active_grant.id}/revoke",
            json=DEFAULT_REVOKE_PAYLOAD,
        )

        assert response.status_code == 401

    def test_rejects_forbidden_role(
        self,
        client,
        auth_headers_for,
        emergency_patient_user,
        emergency_active_grant,
    ):
        headers = auth_headers_for(
            emergency_patient_user,
            role=Role.PATIENT,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_active_grant.id}/revoke",
            json=DEFAULT_REVOKE_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 403

    def test_revokes_request(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_active_grant,
        monkeypatch,
    ):
        emergency_active_grant.status = (
            EmergencyAccessStatus.REVOKED
        )

        called = {}

        def fake_revoke_emergency_access(**kwargs):
            called.update(kwargs)
            return emergency_active_grant

        monkeypatch.setattr(
            emergency_access_route,
            "revoke_emergency_access",
            fake_revoke_emergency_access,
        )

        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_active_grant.id}/revoke",
            json={
                "reason": "Reviewer terminated access.",
            },
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["id"] == (
            emergency_active_grant.id
        )
        assert (
            body["data"]["status"]
            == EmergencyAccessStatus.REVOKED.value
        )

        assert called == {
            "emergency_access_id": (
                emergency_active_grant.id
            ),
            "actor_id": emergency_reviewer.id,
            "reason": "Reviewer terminated access.",
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {
                "reason": "",
            },
            {
                "reason": "   ",
            },
            {
                "reason": 123,
            },
            {
                "reason": "x" * 501,
            },
            {
                "reason": "Valid reason.",
                "unknown_field": "bad",
            },
        ],
    )
    def test_rejects_invalid_revoke_payload(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_active_grant,
        payload,
    ):
        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_active_grant.id}/revoke",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422

    def test_propagates_revoke_not_found_error(
        self,
        client,
        auth_headers_for,
        emergency_reviewer,
        emergency_active_grant,
        monkeypatch,
    ):
        def fake_revoke_emergency_access(**kwargs):
            raise NotFoundError(
                "Emergency access request not found"
            )

        monkeypatch.setattr(
            emergency_access_route,
            "revoke_emergency_access",
            fake_revoke_emergency_access,
        )

        headers = auth_headers_for(
            emergency_reviewer,
        )

        response = client.post(
            f"{REQUEST_ENDPOINT}/{emergency_active_grant.id}/revoke",
            json=DEFAULT_REVOKE_PAYLOAD,
            headers=headers,
        )

        assert response.status_code == 404