from datetime import datetime, timedelta, timezone

from app.core.enums.role_enums import Role


def _headers(make_authenticated_staff, clinic, role):
    _, h = make_authenticated_staff(clinic, role)
    return h


class TestPrescriptionRoutes:
    def test_create_prescription_requires_doctor(self, client, clinic, make_patient, make_drug, make_authenticated_staff, assert_forbidden):
        patient = make_patient(clinic)
        drug = make_drug(clinic)
        pharmacist_headers = _headers(make_authenticated_staff, clinic, Role.PHARMACIST)

        resp = client.post(
            "/prescriptions",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "prescribed_by_id": 1,
                "items": [{"drug_id": drug.id}],
            },
            headers=pharmacist_headers,
        )
        assert_forbidden(resp)

    def test_create_prescription_happy_path(self, client, clinic, make_patient, make_drug, make_authenticated_staff):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        resp = client.post(
            "/prescriptions",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "prescribed_by_id": doctor.id,
                "items": [{"drug_id": drug.id, "quantity": 20, "dosage": "500mg"}],
            },
            headers=headers,
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["status"] == "active"
        assert body["interaction_warnings"] == []

    def test_create_prescription_rejects_duplicate_items_at_schema_layer(
        self, client, clinic, make_patient, make_drug, make_authenticated_staff
    ):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        resp = client.post(
            "/prescriptions",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "prescribed_by_id": doctor.id,
                "items": [{"drug_id": drug.id}, {"drug_id": drug.id}],
            },
            headers=headers,
        )
        # unique-items validator lives on PrescriptionCreateSchema itself
        # -> rejected before the service ever runs.
        assert resp.status_code == 422

    def test_get_prescription_not_found(self, client, clinic, make_authenticated_staff, assert_domain_error):
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)
        resp = client.get("/prescriptions/999999", headers=headers)
        assert_domain_error(resp, 404)

    def test_get_prescription_viewable_by_pharmacist(self, client, clinic, make_patient, make_drug, make_authenticated_staff):
        doctor, doctor_headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        create_resp = client.post(
            "/prescriptions",
            json={
                "clinic_id": clinic.id,
                "patient_id": patient.id,
                "prescribed_by_id": doctor.id,
                "items": [{"drug_id": drug.id}],
            },
            headers=doctor_headers,
        )
        rx_id = create_resp.get_json()["data"]["id"]

        pharmacist_headers = _headers(make_authenticated_staff, clinic, Role.PHARMACIST)
        resp = client.get(f"/prescriptions/{rx_id}", headers=pharmacist_headers)
        assert resp.status_code == 200

    def test_list_patient_prescriptions_active_only_filter(self, client, clinic, make_patient, make_drug, make_authenticated_staff):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        r1 = client.post(
            "/prescriptions",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "prescribed_by_id": doctor.id, "items": [{"drug_id": drug.id}]},
            headers=headers,
        )
        r2 = client.post(
            "/prescriptions",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "prescribed_by_id": doctor.id, "items": [{"drug_id": drug.id}]},
            headers=headers,
        )
        r2_id = r2.get_json()["data"]["id"]
        client.post(f"/prescriptions/{r2_id}/cancel", json={}, headers=headers)

        resp = client.get(f"/prescriptions/patients/{patient.id}?active_only=true", headers=headers)
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.get_json()["data"]}
        assert ids == {r1.get_json()["data"]["id"]}

    def test_cancel_prescription(self, client, clinic, make_patient, make_drug, make_authenticated_staff):
        doctor, headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        create_resp = client.post(
            "/prescriptions",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "prescribed_by_id": doctor.id, "items": [{"drug_id": drug.id}]},
            headers=headers,
        )
        rx_id = create_resp.get_json()["data"]["id"]

        resp = client.post(f"/prescriptions/{rx_id}/cancel", json={"reason": "Duplicate"}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "cancelled"

    def test_complete_prescription_allowed_for_pharmacist(self, client, clinic, make_patient, make_drug, make_authenticated_staff):
        doctor, doctor_headers = make_authenticated_staff(clinic, Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        create_resp = client.post(
            "/prescriptions",
            json={"clinic_id": clinic.id, "patient_id": patient.id, "prescribed_by_id": doctor.id, "items": [{"drug_id": drug.id}]},
            headers=doctor_headers,
        )
        rx_id = create_resp.get_json()["data"]["id"]

        pharmacist_headers = _headers(make_authenticated_staff, clinic, Role.PHARMACIST)
        resp = client.post(f"/prescriptions/{rx_id}/complete", headers=pharmacist_headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "completed"


class TestDrugInteractionRoutes:
    def test_check_interactions_route(self, client, clinic, make_drug, make_authenticated_staff):
        a = make_drug(None)
        b = make_drug(None)
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        admin_headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)
        client.post(
            "/prescriptions/interactions",
            json={"drug_a_id": a.id, "drug_b_id": b.id, "severity": "severe"},
            headers=admin_headers,
        )

        resp = client.post(
            "/prescriptions/interactions/check",
            json={"drug_ids": [a.id, b.id]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["has_interactions"] is True

    def test_check_interactions_rejects_single_drug_at_schema_layer(self, client, clinic, make_drug, make_authenticated_staff):
        a = make_drug(None)
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        resp = client.post(
            "/prescriptions/interactions/check", json={"drug_ids": [a.id]}, headers=headers
        )
        assert resp.status_code == 422

    def test_create_drug_interaction_requires_admin(self, client, clinic, make_drug, make_authenticated_staff, assert_forbidden):
        a = make_drug(None)
        b = make_drug(None)
        headers = _headers(make_authenticated_staff, clinic, Role.DOCTOR)

        resp = client.post(
            "/prescriptions/interactions",
            json={"drug_a_id": a.id, "drug_b_id": b.id, "severity": "mild"},
            headers=headers,
        )
        assert_forbidden(resp)

    def test_create_drug_interaction_rejects_self_at_schema_layer(self, client, clinic, make_drug, make_authenticated_staff):
        a = make_drug(None)
        headers = _headers(make_authenticated_staff, clinic, Role.ADMIN)

        resp = client.post(
            "/prescriptions/interactions",
            json={"drug_a_id": a.id, "drug_b_id": a.id, "severity": "mild"},
            headers=headers,
        )
        assert resp.status_code == 422