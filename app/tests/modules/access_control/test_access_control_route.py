from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.access_control.routes import (
    access_control_routes,
)
from app.modules.access_control.schemas.access_control_schema import (
    AccessControlRoleChangeResponseSchema,
    AccessControlStatusChangeResponseSchema,
    AccessControlUserResponseSchema,
)


# ============================================================================
# HELPERS
# ============================================================================


def route_path(
    app,
    endpoint_name: str,
) -> str:
    """
    Resolve the registered Flask route path by endpoint name.

    This avoids hard-coding whether the Access Control blueprint is mounted
    directly at /access-control or under an application prefix such as /api.
    """
    for rule in app.url_map.iter_rules():
        if rule.endpoint == endpoint_name:
            return rule.rule

    raise AssertionError(
        f"Route endpoint '{endpoint_name}' is not registered"
    )


def valid_role_payload():
    return {
        "role": Role.DOCTOR.value,
    }


def valid_status_payload():
    return {
        "is_active": False,
    }


# ============================================================================
# ROUTE PATHS
# ============================================================================


class TestAccessControlRouteRegistration:
    def test_list_users_route_is_registered(
        self,
        app,
    ):
        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        assert path.endswith(
            "/access-control/users"
        )

    def test_get_user_route_is_registered(
        self,
        app,
    ):
        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        )

        assert path.endswith(
            "/access-control/users/<int:user_id>"
        )

    def test_change_role_route_is_registered(
        self,
        app,
    ):
        path = route_path(
            app,
            "access_control.change_user_role_route",
        )

        assert path.endswith(
            "/access-control/users/<int:user_id>/role"
        )

    def test_change_status_route_is_registered(
        self,
        app,
    ):
        path = route_path(
            app,
            "access_control.change_user_status_route",
        )

        assert path.endswith(
            "/access-control/users/<int:user_id>/status"
        )

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            (
                "access_control.list_access_control_users_route",
                "GET",
            ),
            (
                "access_control.get_access_control_user_route",
                "GET",
            ),
            (
                "access_control.change_user_role_route",
                "PATCH",
            ),
            (
                "access_control.change_user_status_route",
                "PATCH",
            ),
        ],
    )
    def test_access_control_route_methods(
        self,
        app,
        endpoint,
        method,
    ):
        matching_rules = [
            rule
            for rule in app.url_map.iter_rules()
            if rule.endpoint == endpoint
        ]

        assert matching_rules
        assert method in matching_rules[0].methods


# ============================================================================
# CURRENT USER RESOLUTION
# ============================================================================


class TestCurrentUserResolution:
    def test_get_current_user_returns_active_user(
        self,
        app,
        user,
        monkeypatch,
    ):
        monkeypatch.setattr(
            access_control_routes,
            "get_jwt_identity",
            Mock(
                return_value=str(user.id),
            ),
        )

        result = access_control_routes._get_current_user()

        assert result.id == user.id
        assert result.email == user.email

    @pytest.mark.parametrize(
        "identity",
        [
            None,
            "",
            "abc",
            "0",
            "-1",
        ],
    )
    def test_get_current_user_rejects_invalid_identity(
        self,
        app,
        user,
        monkeypatch,
        identity,
    ):
        monkeypatch.setattr(
            access_control_routes,
            "get_jwt_identity",
            Mock(
                return_value=identity,
            ),
        )

        with pytest.raises(
            ValidationError,
            match="Invalid authentication identity",
        ):
            access_control_routes._get_current_user()

    def test_get_current_user_rejects_missing_user(
        self,
        app,
        monkeypatch,
    ):
        monkeypatch.setattr(
            access_control_routes,
            "get_jwt_identity",
            Mock(
                return_value="999999",
            ),
        )

        with pytest.raises(
            ValidationError,
            match="Authenticated user could not be resolved",
        ):
            access_control_routes._get_current_user()

    def test_get_current_user_rejects_inactive_user(
        self,
        app,
        user,
        db_session,
        monkeypatch,
    ):
        user.is_active = False
        db_session.commit()

        monkeypatch.setattr(
            access_control_routes,
            "get_jwt_identity",
            Mock(
                return_value=str(user.id),
            ),
        )

        with pytest.raises(
            ValidationError,
            match="User account is inactive",
        ):
            access_control_routes._get_current_user()


# ============================================================================
# SERIALIZATION
# ============================================================================


class TestAccessControlSerialization:
    def test_serializes_user_response_schema(
        self,
        app,
        user,
    ):
        result = access_control_routes._serialize(
            AccessControlUserResponseSchema,
            user,
        )

        assert result["id"] == user.id
        assert result["email"] == user.email
        assert result["role"] == user.role.value
        assert result["is_active"] is user.is_active
        assert result["clinic_id"] == user.clinic_id

    def test_serializes_role_change_response(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="serialize-role@test.com",
        )

        payload = AccessControlRoleChangeResponseSchema(
            user=AccessControlUserResponseSchema.model_validate(
                target,
                from_attributes=True,
            ),
            previous_role=Role.PATIENT,
            new_role=Role.DOCTOR,
            reason="Promotion",
        )

        result = access_control_routes._serialize(
            AccessControlRoleChangeResponseSchema,
            payload,
        )

        assert result["previous_role"] == Role.PATIENT.value
        assert result["new_role"] == Role.DOCTOR.value
        assert result["reason"] == "Promotion"
        assert result["user"]["id"] == target.id

    def test_serializes_status_change_response(
        self,
        app,
        user,
        make_user,
        clinic,
    ):
        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="serialize-status@test.com",
        )

        payload = AccessControlStatusChangeResponseSchema(
            user=AccessControlUserResponseSchema.model_validate(
                target,
                from_attributes=True,
            ),
            previous_status=True,
            new_status=False,
            reason="Suspension",
        )

        result = access_control_routes._serialize(
            AccessControlStatusChangeResponseSchema,
            payload,
        )

        assert result["previous_status"] is True
        assert result["new_status"] is False
        assert result["reason"] == "Suspension"
        assert result["user"]["id"] == target.id


# ============================================================================
# LIST USERS
# ============================================================================


class TestListAccessControlUsersRoute:
    def test_requires_authentication(
        self,
        app,
        client,
    ):
        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(path)

        assert response.status_code == 401

    def test_rejects_non_admin_user(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        patient = make_user(
            clinic,
            role=Role.PATIENT,
            email="route-patient@test.com",
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(patient),
        )

        assert response.status_code == 403

    def test_admin_can_list_users(
        self,
        app,
        client,
        user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        service_result = [
            AccessControlUserResponseSchema.model_validate(
                user,
                from_attributes=True,
            )
        ]

        service = Mock(
            return_value=(
                service_result,
                1,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["items"] == [
            {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "clinic_id": user.clinic_id,
            }
        ]

        assert body["data"]["pagination"] == {
            "page": 1,
            "per_page": 50,
            "total": 1,
            "pages": 1,
        }

        service.assert_called_once()

        kwargs = service.call_args.kwargs

        assert kwargs["actor_id"] == user.id
        assert kwargs["query"].page == 1
        assert kwargs["query"].per_page == 50

    def test_super_admin_can_list_users(
        self,
        app,
        client,
        make_user,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="route-super-admin@test.com",
        )

        service_result = [
            AccessControlUserResponseSchema.model_validate(
                super_admin,
                from_attributes=True,
            )
        ]

        service = Mock(
            return_value=(
                service_result,
                1,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(super_admin),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["items"][0]["id"] == (
            super_admin.id
        )

        service.assert_called_once()

        kwargs = service.call_args.kwargs

        assert kwargs["actor_id"] == super_admin.id
        assert kwargs["query"].page == 1
        assert kwargs["query"].per_page == 50

    def test_list_accepts_query_filters(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = 1

        service = Mock(
            return_value=(
                [],
                0,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
            query_string={
                "page": "2",
                "per_page": "25",
                "role": Role.DOCTOR.value,
                "is_active": "true",
            },
        )

        assert response.status_code == 200

        kwargs = service.call_args.kwargs
        query = kwargs["query"]

        assert kwargs["actor_id"] == user.id
        assert query.page == 2
        assert query.per_page == 25
        assert query.role is Role.DOCTOR
        assert query.is_active is True

    def test_list_rejects_invalid_query(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
            query_string={
                "page": "0",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_list_rejects_unknown_query_parameter(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
            query_string={
                "unexpected": "value",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_list_handles_empty_result(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN

        service = Mock(
            return_value=(
                [],
                0,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "list_access_control_users",
            service,
        )

        path = route_path(
            app,
            "access_control.list_access_control_users_route",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["items"] == []

        assert body["data"]["pagination"] == {
            "page": 1,
            "per_page": 50,
            "total": 0,
            "pages": 0,
        }


# ============================================================================
# GET USER
# ============================================================================


class TestGetAccessControlUserRoute:
    def test_requires_authentication(
        self,
        app,
        client,
    ):
        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        ).replace(
            "<int:user_id>",
            "1",
        )

        response = client.get(path)

        assert response.status_code == 401

    def test_rejects_non_admin_user(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        patient = make_user(
            clinic,
            role=Role.PATIENT,
            email="get-route-patient@test.com",
        )

        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        ).replace(
            "<int:user_id>",
            str(patient.id),
        )

        response = client.get(
            path,
            headers=auth_headers_for(patient),
        )

        assert response.status_code == 403

    def test_admin_can_get_user(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="get-target@test.com",
        )

        service = Mock(
            return_value=AccessControlUserResponseSchema.model_validate(
                target,
                from_attributes=True,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "get_access_control_user",
            service,
        )

        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == {
            "id": target.id,
            "email": target.email,
            "role": target.role.value,
            "is_active": target.is_active,
            "clinic_id": target.clinic_id,
        }

        service.assert_called_once_with(
            actor_id=user.id,
            user_id=target.id,
        )

    def test_super_admin_can_get_user(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="get-super@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="get-super-target@test.com",
        )

        service = Mock(
            return_value=AccessControlUserResponseSchema.model_validate(
                target,
                from_attributes=True,
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "get_access_control_user",
            service,
        )

        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.get(
            path,
            headers=auth_headers_for(super_admin),
        )

        assert response.status_code == 200

        service.assert_called_once_with(
            actor_id=super_admin.id,
            user_id=target.id,
        )

    def test_get_handles_service_not_found(
        self,
        app,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN

        service = Mock(
            side_effect=NotFoundError(
                "User 999999 not found",
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "get_access_control_user",
            service,
        )

        path = route_path(
            app,
            "access_control.get_access_control_user_route",
        ).replace(
            "<int:user_id>",
            "999999",
        )

        response = client.get(
            path,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "User 999999 not found"
        )


# ============================================================================
# CHANGE USER ROLE
# ============================================================================


class TestChangeUserRoleRoute:
    def test_requires_authentication(
        self,
        app,
        client,
    ):
        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            "1",
        )

        response = client.patch(
            path,
            json=valid_role_payload(),
        )

        assert response.status_code == 401

    def test_admin_is_rejected_by_route_authorization(
        self,
        app,
        client,
        user,
        auth_headers_for,
    ):
        user.role = Role.ADMIN

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(user.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json=valid_role_payload(),
        )

        assert response.status_code == 403

    def test_super_admin_can_change_role(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-route-super@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-route-target@test.com",
        )

        result = Mock(
            return_value={
                "user": AccessControlUserResponseSchema.model_validate(
                    target,
                    from_attributes=True,
                ),
                "previous_role": Role.PATIENT,
                "new_role": Role.DOCTOR,
                "reason": "Clinical promotion",
            },
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            result,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json={
                "role": Role.DOCTOR.value,
                "reason": "Clinical promotion",
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["previous_role"] == (
            Role.PATIENT.value
        )
        assert body["data"]["new_role"] == (
            Role.DOCTOR.value
        )
        assert body["data"]["reason"] == (
            "Clinical promotion"
        )

        result.assert_called_once_with(
            actor_id=super_admin.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
            reason="Clinical promotion",
        )

    def test_role_change_allows_missing_reason(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-no-reason-route@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-no-reason-target@test.com",
        )

        result = Mock(
            return_value={
                "user": AccessControlUserResponseSchema.model_validate(
                    target,
                    from_attributes=True,
                ),
                "previous_role": Role.PATIENT,
                "new_role": Role.DOCTOR,
                "reason": None,
            },
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            result,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json={
                "role": Role.DOCTOR.value,
            },
        )

        assert response.status_code == 200

        result.assert_called_once_with(
            actor_id=super_admin.id,
            user_id=target.id,
            new_role=Role.DOCTOR,
            reason=None,
        )

    def test_role_change_rejects_invalid_body(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="invalid-role-body@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="invalid-role-body-target@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json={},
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_role_change_rejects_unknown_fields(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="unknown-role-field@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="unknown-role-field-target@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json={
                "role": Role.DOCTOR.value,
                "unexpected": "value",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_role_change_rejects_non_object_json(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="non-object-role@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="non-object-role-target@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json=["doctor"],
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "JSON body must be an object"

        service.assert_not_called()

    def test_role_change_handles_domain_error(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="role-domain-error@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="role-domain-target@test.com",
        )

        service = Mock(
            side_effect=ConflictError(
                "Users cannot change their own role",
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_role",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_role_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json=valid_role_payload(),
        )

        assert response.status_code == 409

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Users cannot change their own role"
        )


# ============================================================================
# CHANGE USER STATUS
# ============================================================================


class TestChangeUserStatusRoute:
    def test_requires_authentication(
        self,
        app,
        client,
    ):
        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            "1",
        )

        response = client.patch(
            path,
            json=valid_status_payload(),
        )

        assert response.status_code == 401

    def test_admin_can_change_status(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-route-target@test.com",
        )

        result = Mock(
            return_value={
                "user": AccessControlUserResponseSchema.model_validate(
                    target,
                    from_attributes=True,
                ),
                "previous_status": True,
                "new_status": False,
                "reason": "Suspended",
            },
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            result,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json={
                "is_active": False,
                "reason": "Suspended",
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["previous_status"] is True
        assert body["data"]["new_status"] is False
        assert body["data"]["reason"] == "Suspended"

        result.assert_called_once_with(
            actor_id=user.id,
            user_id=target.id,
            is_active=False,
            reason="Suspended",
        )

    def test_super_admin_can_change_status(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        super_admin = make_user(
            None,
            role=Role.SUPER_ADMIN,
            email="status-route-super@test.com",
        )

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-route-super-target@test.com",
        )

        result = Mock(
            return_value={
                "user": AccessControlUserResponseSchema.model_validate(
                    target,
                    from_attributes=True,
                ),
                "previous_status": True,
                "new_status": False,
                "reason": None,
            },
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            result,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(super_admin),
            json={
                "is_active": False,
            },
        )

        assert response.status_code == 200

        result = result

        result.assert_called_once_with(
            actor_id=super_admin.id,
            user_id=target.id,
            is_active=False,
            reason=None,
        )

    def test_status_change_rejects_non_admin(
        self,
        app,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        patient = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-route-patient@test.com",
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(patient.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(patient),
            json=valid_status_payload(),
        )

        assert response.status_code == 403

    def test_status_change_rejects_missing_body(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="missing-status-body@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_status_change_rejects_unknown_fields(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="unknown-status-field@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json={
                "is_active": False,
                "unexpected": "value",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_status_change_rejects_invalid_is_active(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="invalid-status-value@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json={
                "is_active": "not-a-bool",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert "details" in body

        service.assert_not_called()

    def test_status_change_rejects_non_object_json(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="non-object-status@test.com",
        )

        service = Mock()

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json=False,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "JSON body must be an object"

        service.assert_not_called()

    def test_status_change_handles_domain_error(
        self,
        app,
        client,
        user,
        make_user,
        clinic,
        auth_headers_for,
        monkeypatch,
    ):
        user.role = Role.ADMIN
        user.clinic_id = clinic.id

        target = make_user(
            clinic,
            role=Role.PATIENT,
            email="status-domain-target@test.com",
        )

        service = Mock(
            side_effect=ConflictError(
                "User already has the requested account status",
            ),
        )

        monkeypatch.setattr(
            access_control_routes,
            "change_user_status",
            service,
        )

        path = route_path(
            app,
            "access_control.change_user_status_route",
        ).replace(
            "<int:user_id>",
            str(target.id),
        )

        response = client.patch(
            path,
            headers=auth_headers_for(user),
            json={
                "is_active": True,
            },
        )

        assert response.status_code == 409

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "User already has the requested account status"
        )