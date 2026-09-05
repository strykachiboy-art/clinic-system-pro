from unittest.mock import patch

import pytest

from app.core.enums.ai_enums import AIFeature
from app.core.enums.role_enums import Role
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.ai.routes.ai_route import ai_bp


# ============================================================================
# CLIENT
# ============================================================================

@pytest.fixture()
def ai_client(app):
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)

    return app.test_client()


# ============================================================================
# DRUG INTERACTIONS
# ============================================================================

class TestDrugInteractionsRoute:

    def test_returns_success_for_valid_request(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
        )

        expected = {
            "interaction": "No significant interaction found",
            "risk": "low",
        }

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Amoxicillin",
                        "Paracetamol",
                    ],
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        mock_service.assert_called_once_with(
            clinic_id=clinic.id,
            drug_names=[
                "Amoxicillin",
                "Paracetamol",
            ],
            patient_id=None,
            user_id=mock_service.call_args.kwargs["user_id"],
        )

    def test_passes_patient_id_to_service(
        self,
        ai_client,
        clinic,
        patient,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.DOCTOR,
        )

        expected = {
            "interaction": "No interaction",
            "risk": "low",
        }

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Amoxicillin",
                        "Ibuprofen",
                    ],
                    "patient_id": patient.id,
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        mock_service.assert_called_once()

        kwargs = mock_service.call_args.kwargs

        assert kwargs["clinic_id"] == clinic.id
        assert kwargs["drug_names"] == [
            "Amoxicillin",
            "Ibuprofen",
        ]
        assert kwargs["patient_id"] == patient.id
        assert isinstance(kwargs["user_id"], int)

    def test_passes_current_jwt_user_id_to_service(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        staff, headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
        )

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            return_value={"risk": "low"},
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Drug A",
                        "Drug B",
                    ],
                },
                headers=headers,
            )

        assert response.status_code == 200

        kwargs = mock_service.call_args.kwargs

        assert kwargs["user_id"] == staff.user_id

    def test_rejects_missing_body(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
        )

        response = ai_client.post(
            "/api/ai/drug-interactions",
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_rejects_invalid_drug_names(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
        )

        response = ai_client.post(
            "/api/ai/drug-interactions",
            json={
                "clinic_id": clinic.id,
                "drug_names": ["OnlyOneDrug"],
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_returns_service_validation_error(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.PHARMACIST,
        )

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            side_effect=ValidationError("AI credits exhausted"),
        ):

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Drug A",
                        "Drug B",
                    ],
                },
                headers=headers,
            )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "AI credits exhausted"


# ============================================================================
# TRIAGE
# ============================================================================

class TestTriageRoute:

    def test_returns_success_for_valid_request(
        self,
        ai_client,
        clinic,
        patient,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.NURSE,
        )

        expected = {
            "risk_score": "medium",
            "summary": "Patient requires clinical review",
        }

        with patch(
            "app.modules.ai.routes.ai_route.assist_triage",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/triage",
                json={
                    "clinic_id": clinic.id,
                    "patient_id": patient.id,
                    "symptoms": "Fever and headache",
                    "vitals": {
                        "temperature": 38.5,
                        "heart_rate": 95,
                    },
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        mock_service.assert_called_once()

        kwargs = mock_service.call_args.kwargs

        assert kwargs["clinic_id"] == clinic.id
        assert kwargs["patient_id"] == patient.id
        assert kwargs["symptoms"] == "Fever and headache"
        assert kwargs["vitals"] == {
            "temperature": 38.5,
            "heart_rate": 95,
        }
        assert isinstance(kwargs["user_id"], int)

    def test_accepts_request_without_vitals(
        self,
        ai_client,
        clinic,
        patient,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.DOCTOR,
        )

        expected = {
            "risk_score": "low",
            "summary": "Stable",
        }

        with patch(
            "app.modules.ai.routes.ai_route.assist_triage",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/triage",
                json={
                    "clinic_id": clinic.id,
                    "patient_id": patient.id,
                    "symptoms": "Mild headache",
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        kwargs = mock_service.call_args.kwargs

        assert kwargs["vitals"] is None

    def test_rejects_missing_symptoms(
        self,
        ai_client,
        clinic,
        patient,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.NURSE,
        )

        response = ai_client.post(
            "/api/ai/triage",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_rejects_invalid_vitals(
        self,
        ai_client,
        clinic,
        patient,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.NURSE,
        )

        response = ai_client.post(
            "/api/ai/triage",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "symptoms": "Fever",
                "vitals": "not-an-object",
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_returns_service_not_found_error(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.DOCTOR,
        )

        with patch(
            "app.modules.ai.routes.ai_route.assist_triage",
            side_effect=NotFoundError("Patient 999 not found"),
        ):

            response = ai_client.post(
                "/api/ai/triage",
                json={
                    "clinic_id": clinic.id,
                    "patient_id": 999,
                    "symptoms": "Fever",
                },
                headers=headers,
            )

        assert response.status_code == 404

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Patient 999 not found"


# ============================================================================
# LAB RESULTS
# ============================================================================

class TestLabResultsRoute:

    def test_returns_success_for_valid_request(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.LAB_TECHNICIAN,
        )

        expected = {
            "summary": "Results within expected range",
            "abnormal_values": [],
        }

        with patch(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/lab-results/interpret",
                json={
                    "clinic_id": clinic.id,
                    "result_data": {
                        "hemoglobin": 14.2,
                        "wbc": 6.8,
                    },
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        mock_service.assert_called_once()

        kwargs = mock_service.call_args.kwargs

        assert kwargs["clinic_id"] == clinic.id
        assert kwargs["patient_id"] is None
        assert kwargs["lab_order_id"] is None
        assert kwargs["result_data"] == {
            "hemoglobin": 14.2,
            "wbc": 6.8,
        }
        assert isinstance(kwargs["user_id"], int)

    def test_passes_lab_order_id_to_service(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.LAB_TECHNICIAN,
        )

        expected = {
            "summary": "Lab interpretation",
        }

        with patch(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            return_value=expected,
        ) as mock_service:

            response = ai_client.post(
                "/api/ai/lab-results/interpret",
                json={
                    "clinic_id": clinic.id,
                    "patient_id": 10,
                    "lab_order_id": 25,
                    "result_data": {
                        "glucose": 95,
                    },
                },
                headers=headers,
            )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"] == expected

        kwargs = mock_service.call_args.kwargs

        assert kwargs["clinic_id"] == clinic.id
        assert kwargs["patient_id"] == 10
        assert kwargs["lab_order_id"] == 25
        assert kwargs["result_data"] == {
            "glucose": 95,
        }

    def test_rejects_missing_result_data(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.LAB_TECHNICIAN,
        )

        response = ai_client.post(
            "/api/ai/lab-results/interpret",
            json={
                "clinic_id": clinic.id,
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"

    def test_rejects_empty_result_data(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            Role.LAB_TECHNICIAN,
        )

        response = ai_client.post(
            "/api/ai/lab-results/interpret",
            json={
                "clinic_id": clinic.id,
                "result_data": {},
            },
            headers=headers,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Validation error"
        assert body["details"]

        result_data_error = next(
            (
                detail
                for detail in body["details"]
                if detail.get("loc") == ["result_data"]
            ),
            None,
        )

        assert result_data_error is not None
        assert "Result data is required" in result_data_error["msg"]


# ============================================================================
# AUTHORIZATION
# ============================================================================

class TestAIRouteAuthorization:

    @pytest.mark.parametrize(
        "role",
        [
            Role.ADMIN,
            Role.DOCTOR,
            Role.NURSE,
            Role.PHARMACIST,
            Role.LAB_TECHNICIAN,
        ],
    )
    def test_allowed_roles_can_access_ai_routes(
        self,
        ai_client,
        clinic,
        role,
        make_authenticated_staff,
    ):
        _, headers = make_authenticated_staff(
            clinic,
            role,
        )

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            return_value={"risk": "low"},
        ):

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Drug A",
                        "Drug B",
                    ],
                },
                headers=headers,
            )

        assert response.status_code == 200

    def test_unauthenticated_request_is_rejected(
        self,
        ai_client,
        clinic,
    ):
        response = ai_client.post(
            "/api/ai/drug-interactions",
            json={
                "clinic_id": clinic.id,
                "drug_names": [
                    "Drug A",
                    "Drug B",
                ],
            },
        )

        assert response.status_code in (401, 422)

        body = response.get_json()

        assert body is not None
        assert "msg" in body

    def test_disallowed_role_is_rejected(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
        assert_forbidden,
    ):
        # RECEPTIONIST is intentionally not part of AI_ROLES.
        _, headers = make_authenticated_staff(
            clinic,
            Role.RECEPTIONIST,
        )

        response = ai_client.post(
            "/api/ai/drug-interactions",
            json={
                "clinic_id": clinic.id,
                "drug_names": [
                    "Drug A",
                    "Drug B",
                ],
            },
            headers=headers,
        )

        assert_forbidden(response)

    def test_allowed_jwt_role_claim_can_authorize_request(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
        auth_headers_for,
    ):
        """
        Verify authorization uses the JWT role claim.

        The underlying user/staff has DOCTOR role, while the JWT is
        deliberately created with ADMIN as its role claim. ADMIN is
        allowed by AI_ROLES, so the request should be authorized.
        """
        staff, _ = make_authenticated_staff(
            clinic,
            Role.DOCTOR,
        )

        headers = auth_headers_for(
            staff.user,
            role=Role.ADMIN,
        )

        with patch(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            return_value={"risk": "low"},
        ):

            response = ai_client.post(
                "/api/ai/drug-interactions",
                json={
                    "clinic_id": clinic.id,
                    "drug_names": [
                        "Drug A",
                        "Drug B",
                    ],
                },
                headers=headers,
            )

        assert response.status_code == 200

    def test_disallowed_jwt_role_claim_is_rejected(
        self,
        ai_client,
        clinic,
        make_authenticated_staff,
        auth_headers_for,
        assert_forbidden,
    ):
        """
        Verify that an otherwise valid user cannot gain access when
        the JWT role claim itself is not allowed.
        """
        staff, _ = make_authenticated_staff(
            clinic,
            Role.DOCTOR,
        )

        headers = auth_headers_for(
            staff.user,
            role=Role.RECEPTIONIST,
        )

        response = ai_client.post(
            "/api/ai/drug-interactions",
            json={
                "clinic_id": clinic.id,
                "drug_names": [
                    "Drug A",
                    "Drug B",
                ],
            },
            headers=headers,
        )

        assert_forbidden(response)
