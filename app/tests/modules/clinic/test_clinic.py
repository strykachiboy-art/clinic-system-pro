import pytest

from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.clinic.routes import clinic_route


# ============================================================================
# HELPERS
# ============================================================================

def make_auth_headers(auth_headers_for, user, role=None):
    return auth_headers_for(user, role=role)


def assert_error(response, status_code, message=None):
    assert response.status_code == status_code, response.get_json()

    body = response.get_json()

    assert "error" in body

    if message is not None:
        assert body["error"] == message

    return body


# ============================================================================
# SERIALIZATION
# ============================================================================

class TestSerializeClinic:

    def test_serializes_clinic(self, clinic):
        data = clinic_route._serialize_clinic(clinic)

        assert data["id"] == clinic.id
        assert data["name"] == clinic.name
        assert data["clinic_type"] == clinic.clinic_type.value
        assert data["status"] == clinic.status.value
        assert data["parent_clinic_id"] == clinic.parent_clinic_id
        assert data["is_headquarters"] == clinic.is_headquarters
        assert data["address"] == clinic.address
        assert data["city"] == clinic.city
        assert data["country"] == clinic.country
        assert data["phone"] == clinic.phone
        assert data["email"] == clinic.email
        assert data["timezone"] == clinic.timezone
        assert data["ai_credits"] == clinic.ai_credits
        assert (
            data["ai_requests_this_month"]
            == clinic.ai_requests_this_month
        )

    def test_serializes_none_times_as_none(self, clinic):
        clinic.opening_time = None
        clinic.closing_time = None

        data = clinic_route._serialize_clinic(clinic)

        assert data["opening_time"] is None
        assert data["closing_time"] is None

    def test_serializes_times(self, clinic):
        from datetime import time

        clinic.opening_time = time(8, 0)
        clinic.closing_time = time(17, 0)

        data = clinic_route._serialize_clinic(clinic)

        assert data["opening_time"] == "08:00:00"
        assert data["closing_time"] == "17:00:00"

    def test_serializes_created_and_updated_dates(self, clinic):
        data = clinic_route._serialize_clinic(clinic)

        assert data["created_at"] is not None
        assert data["updated_at"] is not None


# ============================================================================
# JSON VALIDATION
# ============================================================================

class TestValidateJson:

    def test_valid_payload_returns_schema_instance(self, app):
        from app.modules.clinic.schemas.clinic_schema import (
            ClinicCreateSchema,
        )

        with app.test_request_context(
            "/api/clinics",
            method="POST",
            json={"name": "New Clinic"},
        ):
            payload, error = clinic_route._validate_json(
                ClinicCreateSchema
            )

        assert error is None
        assert payload is not None
        assert payload.name == "New Clinic"

    def test_invalid_payload_returns_400(self, app):
        from app.modules.clinic.schemas.clinic_schema import (
            ClinicCreateSchema,
        )

        with app.test_request_context(
            "/api/clinics",
            method="POST",
            json={},
        ):
            payload, error = clinic_route._validate_json(
                ClinicCreateSchema
            )

        assert payload is None
        assert error is not None

        response, status = error

        assert status == 400

        body = response.get_json()

        assert body["error"] == "Validation error"
        assert "details" in body

    def test_invalid_enum_returns_400(self, app):
        from app.modules.clinic.schemas.clinic_schema import (
            ClinicCreateSchema,
        )

        with app.test_request_context(
            "/api/clinics",
            method="POST",
            json={
                "name": "Test Clinic",
                "clinic_type": "invalid",
            },
        ):
            payload, error = clinic_route._validate_json(
                ClinicCreateSchema
            )

        assert payload is None
        assert error is not None

        response, status = error

        assert status == 400
        assert response.get_json()["error"] == "Validation error"

    def test_unknown_update_field_is_rejected(self, app):
        from app.modules.clinic.schemas.clinic_schema import (
            ClinicUpdateSchema,
        )

        with app.test_request_context(
            "/api/clinics/1",
            method="PATCH",
            json={
                "unknown_field": "value",
            },
        ):
            payload, error = clinic_route._validate_json(
                ClinicUpdateSchema
            )

        assert payload is None
        assert error is not None

        response, status = error

        assert status == 400
        assert response.get_json()["error"] == "Validation error"


# ============================================================================
# STATUS PARSING
# ============================================================================

class TestParseStatus:

    def test_missing_status_returns_none(self, app):
        with app.test_request_context("/api/clinics"):
            result = clinic_route._parse_status()

        assert result is None

    def test_valid_status_returns_enum(self, app):
        with app.test_request_context(
            "/api/clinics?status=active"
        ):
            result = clinic_route._parse_status()

        assert result == ClinicStatus.ACTIVE

    def test_suspended_status_returns_enum(self, app):
        with app.test_request_context(
            "/api/clinics?status=suspended"
        ):
            result = clinic_route._parse_status()

        assert result == ClinicStatus.SUSPENDED

    def test_inactive_status_returns_enum(self, app):
        with app.test_request_context(
            "/api/clinics?status=inactive"
        ):
            result = clinic_route._parse_status()

        assert result == ClinicStatus.INACTIVE

    def test_invalid_status_returns_400(self, app):
        with app.test_request_context(
            "/api/clinics?status=invalid"
        ):
            result = clinic_route._parse_status()

        response, status = result

        assert status == 400

        body = response.get_json()

        assert body["error"] == (
            "Invalid clinic status 'invalid'"
        )


# ============================================================================
# AUTHENTICATION / AUTHORIZATION
# ============================================================================

class TestClinicRouteAuthorization:

    def test_create_clinic_requires_authentication(self, client):
        response = client.post(
            "/api/clinics",
            json={"name": "New Clinic"},
        )

        assert response.status_code in (401, 422)

    def test_list_clinics_requires_authentication(self, client):
        response = client.get("/api/clinics")

        assert response.status_code in (401, 422)

    def test_get_clinic_requires_authentication(
        self,
        client,
        clinic,
    ):
        response = client.get(
            f"/api/clinics/{clinic.id}"
        )

        assert response.status_code in (401, 422)

    def test_create_clinic_requires_admin(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        user = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "New Clinic"},
            headers=headers,
        )

        assert response.status_code == 403

        body = response.get_json()

        assert body["error"] == "Insufficient permissions"

    def test_admin_can_create_clinic(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "New Clinic"},
            headers=headers,
        )

        assert response.status_code == 201

    @pytest.mark.parametrize(
        "role",
        [
            Role.ADMIN,
            Role.DOCTOR,
            Role.NURSE,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
            Role.RECEPTIONIST,
            Role.PARAMEDIC,
            Role.EMT,
            Role.DRIVER,
            Role.AMBULANCE_DISPATCHER,
            Role.AMBULANCE_COORDINATOR,
        ],
    )
    def test_view_roles_can_list_clinics(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
        role,
    ):
        user = make_user(
            clinic,
            role=role,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics",
            headers=headers,
        )

        assert response.status_code == 200

    def test_doctor_cannot_update_clinic(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        user = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={"name": "Updated"},
            headers=headers,
        )

        assert response.status_code == 403

        body = response.get_json()

        assert body["error"] == "Insufficient permissions"

    def test_doctor_cannot_create_branch(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        user = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/branches",
            json={"name": "Branch"},
            headers=headers,
        )

        assert response.status_code == 403

    def test_doctor_cannot_change_status(
        self,
        client,
        make_user,
        clinic,
        auth_headers_for,
    ):
        user = make_user(
            clinic,
            role=Role.DOCTOR,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/status",
            json={"status": "suspended"},
            headers=headers,
        )

        assert response.status_code == 403


# ============================================================================
# CREATE CLINIC
# ============================================================================

class TestCreateClinicRoute:

    def test_creates_clinic(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "New Clinic"},
            headers=headers,
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["message"] == (
            "Clinic created successfully"
        )

        assert "data" in body
        assert body["data"]["name"] == "New Clinic"
        assert body["data"]["clinic_type"] == "general"
        assert body["data"]["status"] == "active"

    def test_creates_clinic_with_full_payload(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={
                "name": "Full Clinic",
                "clinic_type": "specialist",
                "is_headquarters": True,
                "address": "123 Medical Road",
                "city": "Port Harcourt",
                "country": "Nigeria",
                "phone": "08012345678",
                "email": "clinic@test.com",
                "timezone": "Africa/Lagos",
                "opening_time": "08:00:00",
                "closing_time": "17:00:00",
            },
            headers=headers,
        )

        assert response.status_code == 201

        data = response.get_json()["data"]

        assert data["name"] == "Full Clinic"
        assert data["clinic_type"] == "specialist"
        assert data["is_headquarters"] is True
        assert data["address"] == "123 Medical Road"
        assert data["city"] == "Port Harcourt"
        assert data["country"] == "Nigeria"
        assert data["phone"] == "08012345678"
        assert data["email"] == "clinic@test.com"
        assert data["timezone"] == "Africa/Lagos"
        assert data["opening_time"] == "08:00:00"
        assert data["closing_time"] == "17:00:00"

    def test_missing_name_returns_400(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"
        assert "details" in body

    def test_blank_name_returns_400(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "   "},
            headers=headers,
        )

        assert response.status_code == 400

    def test_missing_parent_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={
                "name": "Child Clinic",
                "parent_clinic_id": 99999,
            },
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == (
            "Parent clinic 99999 not found"
        )

    def test_duplicate_clinic_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={"name": clinic.name},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert "already exists" in body["error"]

    def test_creates_headquarters(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics",
            json={
                "name": "Headquarters",
                "is_headquarters": True,
            },
            headers=headers,
        )

        assert response.status_code == 201

        data = response.get_json()["data"]

        assert data["is_headquarters"] is True
        assert data["parent_clinic_id"] is None


# ============================================================================
# LIST CLINICS
# ============================================================================

class TestListClinicsRoute:

    def test_lists_clinics(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        make_clinic(name="Alpha Clinic")
        make_clinic(name="Beta Clinic")

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert "data" in body
        assert isinstance(body["data"], list)

        names = [
            item["name"]
            for item in body["data"]
        ]

        assert names == sorted(names)

    def test_filters_by_active_status(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        # The default `user` fixture's clinic is also ACTIVE,
        # so create an isolated inactive/suspended set and assert
        # by returned names rather than assuming only one active clinic.
        active = make_clinic(
            name="Active Clinic",
            status=ClinicStatus.ACTIVE,
        )

        make_clinic(
            name="Suspended Clinic",
            status=ClinicStatus.SUSPENDED,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics?status=active",
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        names = {item["name"] for item in data}

        assert active.name in names
        assert "Suspended Clinic" not in names

        for item in data:
            assert item["status"] == "active"

    def test_filters_by_suspended_status(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        make_clinic(
            name="Active Clinic",
            status=ClinicStatus.ACTIVE,
        )

        suspended = make_clinic(
            name="Suspended Clinic",
            status=ClinicStatus.SUSPENDED,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics?status=suspended",
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert len(data) == 1
        assert data[0]["name"] == suspended.name
        assert data[0]["status"] == "suspended"

    def test_invalid_status_returns_400(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics?status=invalid",
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == (
            "Invalid clinic status 'invalid'"
        )


# ============================================================================
# GET CLINIC
# ============================================================================

class TestGetClinicRoute:

    def test_gets_clinic(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            f"/api/clinics/{clinic.id}",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert "data" in body
        assert body["data"]["id"] == clinic.id
        assert body["data"]["name"] == clinic.name

    def test_missing_clinic_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics/99999",
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"


# ============================================================================
# LIST BRANCHES
# ============================================================================

class TestListClinicBranchesRoute:

    def test_lists_branches(
        self,
        client,
        user,
        clinic,
        make_clinic,
        auth_headers_for,
    ):
        branch_one = make_clinic(
            name="Branch One",
            parent_clinic_id=clinic.id,
        )

        branch_two = make_clinic(
            name="Branch Two",
            parent_clinic_id=clinic.id,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            f"/api/clinics/{clinic.id}/branches",
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        ids = {item["id"] for item in data}

        assert ids == {
            branch_one.id,
            branch_two.id,
        }

    def test_branches_are_sorted_by_name(
        self,
        client,
        user,
        clinic,
        make_clinic,
        auth_headers_for,
    ):
        make_clinic(
            name="Zulu Branch",
            parent_clinic_id=clinic.id,
        )

        make_clinic(
            name="Alpha Branch",
            parent_clinic_id=clinic.id,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            f"/api/clinics/{clinic.id}/branches",
            headers=headers,
        )

        assert response.status_code == 200

        names = [
            item["name"]
            for item in response.get_json()["data"]
        ]

        assert names == sorted(names)

    def test_missing_parent_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.get(
            "/api/clinics/99999/branches",
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"


# ============================================================================
# CREATE BRANCH
# ============================================================================

class TestCreateClinicBranchRoute:

    def test_creates_branch(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/branches",
            json={"name": "New Branch"},
            headers=headers,
        )

        assert response.status_code == 201

        body = response.get_json()

        assert body["message"] == (
            "Clinic branch created successfully"
        )

        data = body["data"]

        assert data["name"] == "New Branch"
        assert data["parent_clinic_id"] == clinic.id
        assert data["status"] == "active"
        assert data["is_headquarters"] is False

    def test_creates_branch_with_full_payload(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/branches",
            json={
                "name": "Dental Branch",
                "clinic_type": "dental",
                "address": "456 Branch Road",
                "city": "Lagos",
                "country": "Nigeria",
                "phone": "08111111111",
                "email": "branch@test.com",
                "timezone": "Africa/Lagos",
                "opening_time": "07:30:00",
                "closing_time": "18:30:00",
            },
            headers=headers,
        )

        assert response.status_code == 201

        data = response.get_json()["data"]

        assert data["name"] == "Dental Branch"
        assert data["clinic_type"] == "dental"
        assert data["address"] == "456 Branch Road"
        assert data["city"] == "Lagos"
        assert data["country"] == "Nigeria"
        assert data["phone"] == "08111111111"
        assert data["email"] == "branch@test.com"
        assert data["timezone"] == "Africa/Lagos"
        assert data["opening_time"] == "07:30:00"
        assert data["closing_time"] == "18:30:00"

    def test_missing_parent_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics/99999/branches",
            json={"name": "Branch"},
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == (
            "Parent clinic 99999 not found"
        )

    def test_invalid_payload_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/branches",
            json={},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"

    def test_duplicate_branch_name_returns_400(
        self,
        client,
        user,
        clinic,
        make_clinic,
        auth_headers_for,
    ):
        make_clinic(
            name="Existing Branch",
            parent_clinic_id=clinic.id,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/branches",
            json={"name": "Existing Branch"},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert "already exists" in body["error"]


# ============================================================================
# UPDATE BRANCH CONFIGURATION
# ============================================================================

class TestUpdateClinicBranchConfigurationRoute:

    def test_assigns_parent(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        parent = make_clinic(name="Parent")
        child = make_clinic(name="Child")

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{child.id}/branch-configuration",
            json={
                "parent_clinic_id": parent.id,
            },
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["parent_clinic_id"] == parent.id
        assert data["is_headquarters"] is False

    def test_makes_root_clinic_headquarters(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/branch-configuration",
            json={
                "is_headquarters": True,
            },
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["is_headquarters"] is True
        assert data["parent_clinic_id"] is None

    def test_detaches_clinic_from_parent(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        parent = make_clinic(name="Parent")
        child = make_clinic(
            name="Child",
            parent_clinic_id=parent.id,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{child.id}/branch-configuration",
            json={
                "parent_clinic_id": None,
            },
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["parent_clinic_id"] is None

    def test_self_parent_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/branch-configuration",
            json={
                "parent_clinic_id": clinic.id,
            },
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == (
            "A clinic cannot be its own parent"
        )

    def test_missing_parent_returns_404(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/branch-configuration",
            json={
                "parent_clinic_id": 99999,
            },
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == (
            "Parent clinic 99999 not found"
        )

    def test_headquarters_with_parent_returns_400(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        parent = make_clinic(name="Parent")
        child = make_clinic(name="Child")

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{child.id}/branch-configuration",
            json={
                "parent_clinic_id": parent.id,
                "is_headquarters": True,
            },
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == (
            "A headquarters clinic cannot have a parent clinic"
        )

    def test_circular_hierarchy_returns_400(
        self,
        client,
        user,
        make_clinic,
        auth_headers_for,
    ):
        parent = make_clinic(name="Parent")
        child = make_clinic(
            name="Child",
            parent_clinic_id=parent.id,
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{parent.id}/branch-configuration",
            json={
                "parent_clinic_id": child.id,
            },
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == (
            "This parent assignment would create a circular "
            "clinic hierarchy"
        )

    def test_invalid_payload_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/branch-configuration",
            json={
                "invalid_field": True,
            },
            headers=headers,
        )

        assert response.status_code == 400


# ============================================================================
# UPDATE CLINIC
# ============================================================================

class TestUpdateClinicRoute:

    def test_updates_clinic(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={
                "name": "Updated Clinic",
                "clinic_type": "specialist",
                "city": "Lagos",
            },
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["message"] == (
            "Clinic updated successfully"
        )

        data = body["data"]

        assert data["name"] == "Updated Clinic"
        assert data["clinic_type"] == "specialist"
        assert data["city"] == "Lagos"

    def test_updates_single_field(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        original_name = clinic.name

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={"city": "Abuja"},
            headers=headers,
        )

        assert response.status_code == 200

        data = response.get_json()["data"]

        assert data["city"] == "Abuja"
        assert data["name"] == original_name

    def test_missing_clinic_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            "/api/clinics/99999",
            json={"name": "Updated"},
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"

    def test_invalid_payload_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={"invalid_field": "value"},
            headers=headers,
        )

        assert response.status_code == 400

    def test_blank_name_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={"name": "   "},
            headers=headers,
        )

        assert response.status_code == 400

    def test_duplicate_name_returns_400(
        self,
        client,
        user,
        clinic,
        make_clinic,
        auth_headers_for,
    ):
        other = make_clinic(
            name="Existing Clinic",
        )

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}",
            json={"name": other.name},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert "already exists" in body["error"]


# ============================================================================
# STATUS
# ============================================================================

class TestUpdateClinicStatusRoute:

    def test_changes_status(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/status",
            json={"status": "suspended"},
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["message"] == (
            "Clinic status updated successfully"
        )

        assert body["data"]["status"] == "suspended"

    def test_changes_to_inactive(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/status",
            json={"status": "inactive"},
            headers=headers,
        )

        assert response.status_code == 200
        assert (
            response.get_json()["data"]["status"]
            == "inactive"
        )

    def test_missing_clinic_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            "/api/clinics/99999/status",
            json={"status": "suspended"},
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"

    def test_invalid_status_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/status",
            json={"status": "invalid-status"},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"


# ============================================================================
# AI CREDITS
# ============================================================================

class TestUpdateClinicAICreditsRoute:

    def test_adds_ai_credits(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        original = clinic.ai_credits

        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/ai-credits",
            json={"amount": 25},
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["message"] == (
            "Clinic AI credits updated successfully"
        )

        assert (
            body["data"]["ai_credits"]
            == original + 25
        )

    def test_zero_amount_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/ai-credits",
            json={"amount": 0},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"

    def test_negative_amount_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/ai-credits",
            json={"amount": -5},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"

    def test_missing_amount_returns_400(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            f"/api/clinics/{clinic.id}/ai-credits",
            json={},
            headers=headers,
        )

        assert response.status_code == 400

        body = response.get_json()

        assert body["error"] == "Validation error"

    def test_missing_clinic_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.patch(
            "/api/clinics/99999/ai-credits",
            json={"amount": 10},
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"


# ============================================================================
# API TOKEN
# ============================================================================

class TestRegenerateClinicAPITokenRoute:

    def test_regenerates_api_token(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/api-token/regenerate",
            headers=headers,
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["message"] == (
            "Clinic API token regenerated successfully"
        )

        assert "data" in body
        assert "api_token" in body["data"]

        token = body["data"]["api_token"]

        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_is_stored_on_clinic(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
        db,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            f"/api/clinics/{clinic.id}/api-token/regenerate",
            headers=headers,
        )

        assert response.status_code == 200

        token = response.get_json()["data"]["api_token"]

        db.session.refresh(clinic)

        assert clinic.api_token == token

    def test_regeneration_replaces_old_token(
        self,
        client,
        user,
        clinic,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        first_response = client.post(
            f"/api/clinics/{clinic.id}/api-token/regenerate",
            headers=headers,
        )

        second_response = client.post(
            f"/api/clinics/{clinic.id}/api-token/regenerate",
            headers=headers,
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200

        first_token = (
            first_response
            .get_json()["data"]["api_token"]
        )

        second_token = (
            second_response
            .get_json()["data"]["api_token"]
        )

        assert first_token != second_token

    def test_missing_clinic_returns_404(
        self,
        client,
        user,
        auth_headers_for,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        response = client.post(
            "/api/clinics/99999/api-token/regenerate",
            headers=headers,
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["error"] == "Clinic 99999 not found"


# ============================================================================
# SERVICE EXCEPTION MAPPING
# ============================================================================

class TestClinicRouteExceptionMapping:

    def test_create_clinic_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_create_clinic(**kwargs):
            raise NotFoundError(
                "Parent clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "create_clinic",
            fake_create_clinic,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "Test Clinic"},
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Parent clinic 123 not found"
        )

    def test_create_clinic_maps_validation_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_create_clinic(**kwargs):
            raise ValidationError("Invalid clinic")

        monkeypatch.setattr(
            clinic_route,
            "create_clinic",
            fake_create_clinic,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "Test Clinic"},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Invalid clinic"
        )

    def test_create_clinic_maps_conflict_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_create_clinic(**kwargs):
            raise ConflictError(
                "Clinic already exists"
            )

        monkeypatch.setattr(
            clinic_route,
            "create_clinic",
            fake_create_clinic,
        )

        response = client.post(
            "/api/clinics",
            json={"name": "Test Clinic"},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Clinic already exists"
        )

    def test_get_clinic_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_get_clinic(clinic_id):
            raise NotFoundError(
                f"Clinic {clinic_id} not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "get_clinic",
            fake_get_clinic,
        )

        response = client.get(
            "/api/clinics/123",
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_list_branches_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_list_branches(clinic_id):
            raise NotFoundError(
                f"Clinic {clinic_id} not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "list_branches",
            fake_list_branches,
        )

        response = client.get(
            "/api/clinics/123/branches",
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_update_clinic_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_update_clinic(**kwargs):
            raise NotFoundError(
                "Clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "update_clinic",
            fake_update_clinic,
        )

        response = client.patch(
            "/api/clinics/123",
            json={"name": "Updated"},
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_update_clinic_maps_validation_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_update_clinic(**kwargs):
            raise ValidationError(
                "Invalid update"
            )

        monkeypatch.setattr(
            clinic_route,
            "update_clinic",
            fake_update_clinic,
        )

        response = client.patch(
            "/api/clinics/123",
            json={"name": "Updated"},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Invalid update"
        )

    def test_update_branch_configuration_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_update_branch_configuration(**kwargs):
            raise NotFoundError(
                "Clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "update_branch_configuration",
            fake_update_branch_configuration,
        )

        response = client.patch(
            "/api/clinics/123/branch-configuration",
            json={"is_headquarters": True},
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_update_branch_configuration_maps_validation_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_update_branch_configuration(**kwargs):
            raise ValidationError(
                "Invalid branch configuration"
            )

        monkeypatch.setattr(
            clinic_route,
            "update_branch_configuration",
            fake_update_branch_configuration,
        )

        response = client.patch(
            "/api/clinics/123/branch-configuration",
            json={"is_headquarters": True},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Invalid branch configuration"
        )

    def test_status_update_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_change_status(**kwargs):
            raise NotFoundError(
                "Clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "change_status",
            fake_change_status,
        )

        response = client.patch(
            "/api/clinics/123/status",
            json={"status": "active"},
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_status_update_maps_validation_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_change_status(**kwargs):
            raise ValidationError(
                "Invalid status change"
            )

        monkeypatch.setattr(
            clinic_route,
            "change_status",
            fake_change_status,
        )

        response = client.patch(
            "/api/clinics/123/status",
            json={"status": "active"},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Invalid status change"
        )

    def test_ai_credit_update_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_add_ai_credits(**kwargs):
            raise NotFoundError(
                "Clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "add_ai_credits",
            fake_add_ai_credits,
        )

        response = client.patch(
            "/api/clinics/123/ai-credits",
            json={"amount": 10},
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )

    def test_ai_credit_update_maps_validation_to_400(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_add_ai_credits(**kwargs):
            raise ValidationError(
                "Insufficient AI credits"
            )

        monkeypatch.setattr(
            clinic_route,
            "add_ai_credits",
            fake_add_ai_credits,
        )

        response = client.patch(
            "/api/clinics/123/ai-credits",
            json={"amount": 10},
            headers=headers,
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == (
            "Insufficient AI credits"
        )

    def test_token_regeneration_maps_not_found_to_404(
        self,
        client,
        user,
        auth_headers_for,
        monkeypatch,
    ):
        headers = make_auth_headers(
            auth_headers_for,
            user,
        )

        def fake_regenerate_api_token(**kwargs):
            raise NotFoundError(
                "Clinic 123 not found"
            )

        monkeypatch.setattr(
            clinic_route,
            "regenerate_api_token",
            fake_regenerate_api_token,
        )

        response = client.post(
            "/api/clinics/123/api-token/regenerate",
            headers=headers,
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == (
            "Clinic 123 not found"
        )