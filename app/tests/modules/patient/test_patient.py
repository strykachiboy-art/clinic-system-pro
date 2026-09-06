from app.core.enums.role_enums import Role


def _headers(make_authenticated_staff, clinic, role):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestPatientRoutes:
    def test_create_patient_requires_receptionist_or_admin(
        self, client, clinic, make_authenticated_staff, assert_forbidden
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.NURSE)
        resp = client.post("/api/patients", json={"first_name": "A", "last_name": "B"}, headers=headers)
        assert_forbidden(resp)

    def test_create_patient_happy_path_uses_own_clinic(self, client, clinic, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        resp = client.post(
            "/api/patients", json={"first_name": "Jane", "last_name": "Doe"}, headers=headers
        )
        assert resp.status_code == 201
        body = resp.get_json()["data"]
        assert body["clinic_id"] == clinic.id
        assert body["first_name"] == "Jane"

    def test_create_patient_rejects_invalid_email_at_schema_layer(
        self, client, clinic, make_authenticated_staff
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)
        resp = client.post(
            "/api/patients",
            json={"first_name": "A", "last_name": "B", "email": "not-an-email"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_get_patient_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.get("/api/patients/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_list_patients_search(self, client, clinic, make_patient, make_authenticated_staff):
        make_patient(clinic, first_name="Alice")
        make_patient(clinic, first_name="Bob")
        headers = _headers(make_authenticated_staff, clinic, Role.PHARMACIST)

        resp = client.get(f"/api/patients?clinic_id={clinic.id}&search=alice", headers=headers)
        assert resp.status_code == 200
        names = {p["first_name"] for p in resp.get_json()["data"]}
        assert names == {"Alice"}

    def test_update_patient(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        resp = client.patch(f"/api/patients/{patient.id}", json={"first_name": "New"}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["first_name"] == "New"

    def test_set_patient_status(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)
        resp = client.patch(f"/api/patients/{patient.id}/status", json={"is_active": False}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["is_active"] is False


class TestFamilyMemberRoutes:
    def test_add_and_list_family_member(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        add_resp = client.post(
            f"/api/patients/{patient.id}/family",
            json={"full_name": "John Doe", "relation": "spouse"},
            headers=headers,
        )
        assert add_resp.status_code == 201

        list_resp = client.get(f"/api/patients/{patient.id}/family", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()["data"]) == 1

    def test_update_and_remove_family_member(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        add_resp = client.post(
            f"/api/patients/{patient.id}/family",
            json={"full_name": "Old", "relation": "child"},
            headers=headers,
        )
        member_id = add_resp.get_json()["data"]["id"]

        update_resp = client.patch(
            f"/api/patients/{patient.id}/family/{member_id}",
            json={"full_name": "New"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["data"]["full_name"] == "New"

        delete_resp = client.delete(f"/api/patients/{patient.id}/family/{member_id}", headers=headers)
        assert delete_resp.status_code == 200


class TestInsuranceRoutes:
    def test_add_and_list_insurance(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)

        add_resp = client.post(
            f"/api/patients/{patient.id}/insurance",
            json={"provider_name": "Acme", "policy_number": "P1"},
            headers=headers,
        )
        assert add_resp.status_code == 201

        view_headers = _headers(make_authenticated_staff, clinic, Role.ACCOUNTANT)
        list_resp = client.get(f"/api/patients/{patient.id}/insurance", headers=view_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()["data"]) == 1

    def test_update_insurance(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        add_resp = client.post(
            f"/api/patients/{patient.id}/insurance",
            json={"provider_name": "Acme", "policy_number": "P1"},
            headers=headers,
        )
        insurance_id = add_resp.get_json()["data"]["id"]

        update_resp = client.patch(
            f"/api/patients/{patient.id}/insurance/{insurance_id}",
            json={"is_active": False},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["data"]["is_active"] is False


class TestVitalsRoutes:
    def test_record_and_get_latest_vitals(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.NURSE)

        record_resp = client.post(
            f"/api/patients/{patient.id}/vitals", json={"heart_rate": 75}, headers=headers
        )
        assert record_resp.status_code == 201

        latest_resp = client.get(f"/api/patients/{patient.id}/vitals/latest", headers=headers)
        assert latest_resp.status_code == 200
        assert latest_resp.get_json()["data"]["heart_rate"] == 75

    def test_get_latest_vitals_null_when_none_recorded(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.get(f"/api/patients/{patient.id}/vitals/latest", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"] is None

    def test_get_vitals_history(self, client, clinic, patient, make_authenticated_staff):
        headers = _headers(make_authenticated_staff, clinic, Role.NURSE)
        client.post(f"/api/patients/{patient.id}/vitals", json={"heart_rate": 60}, headers=headers)
        client.post(f"/api/patients/{patient.id}/vitals", json={"heart_rate": 90}, headers=headers)

        resp = client.get(f"/api/patients/{patient.id}/vitals", headers=headers)
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) == 2

    def test_record_vitals_requires_clinical_role(
        self, client, clinic, patient, make_authenticated_staff, assert_forbidden
    ):
        headers = _headers(make_authenticated_staff, clinic, Role.RECEPTIONIST)
        resp = client.post(f"/api/patients/{patient.id}/vitals", json={"heart_rate": 75}, headers=headers)
        assert_forbidden(resp)