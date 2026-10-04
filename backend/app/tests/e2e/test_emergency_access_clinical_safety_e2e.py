from __future__ import annotations

from app.core.audit.models.audit_model import AuditLog
from app.core.clinical_safety.services.medication_safety_service import (
    evaluate_medication_safety,
)
from app.core.emergency_access.services.consent_guard_service import (
    evaluate_consent_guard,
)
from app.core.emergency_access.services.emergency_access_service import (
    assert_emergency_access,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
    EmergencyAccessStatus,
)
from app.core.enums.role_enums import Role
from app.core.clinical_safety.models.clinical_rule_model import (
    ClinicalRule,
)
from app.modules.patient.models.patient_model import Patient
from app.modules.prescription.models.prescription_model import (
    Prescription,
)


def test_emergency_access_clinical_safety_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    make_staff,
    make_patient,
    e2e_login,
):
    admin = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        email="e2e-g8-admin@test.com",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-g8-doctor@test.com",
        },
    )

    receptionist = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
        email="e2e-g8-receptionist@test.com",
    )

    admin_login = e2e_login(
        "e2e-g8-admin@test.com",
    )

    doctor_login = e2e_login(
        "e2e-g8-doctor@test.com",
    )

    receptionist_login = e2e_login(
        "e2e-g8-receptionist@test.com",
    )

    assert admin_login["role"] == Role.ADMIN.value
    assert doctor_login["role"] == Role.DOCTOR.value
    assert receptionist_login["role"] == Role.RECEPTIONIST.value

    # =========================================================================
    # PATIENT
    # =========================================================================

    patient_response = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Gate",
            "last_name": "Eight",
        },
        headers={
            "Authorization": (
                f"Bearer {receptionist_login['access_token']}"
            ),
        },
    )

    assert patient_response.status_code == 201, (
        patient_response.get_json()
    )

    patient_body = patient_response.get_json()

    assert patient_body["success"] is True
    assert patient_body["data"]["clinic_id"] == clinic.id

    patient_id = patient_body["data"]["id"]

    persisted_patient = db.session.get(
        Patient,
        patient_id,
    )

    assert persisted_patient is not None
    assert persisted_patient.clinic_id == clinic.id

    # =========================================================================
    # EMERGENCY ACCESS REQUEST
    # =========================================================================

    request_response = client.post(
        "/api/v1/emergency-access/requests",
        json={
            "patient_id": patient_id,
            "reason": "Immediate emergency treatment required.",
            "purpose": "Emergency clinical care.",
            "scope": [
                "patient:read",
            ],
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert request_response.status_code == 201, (
        request_response.get_json()
    )

    request_body = request_response.get_json()

    assert request_body["success"] is True
    assert (
        request_body["data"]["status"]
        == EmergencyAccessStatus.REQUESTED.value
    )
    assert request_body["data"]["clinic_id"] == clinic.id
    assert request_body["data"]["patient_id"] == patient_id
    assert (
        request_body["data"]["requester_user_id"]
        == doctor_staff.user.id
    )
    assert request_body["data"]["scope"] == [
        "patient:read",
    ]

    emergency_access_id = request_body["data"]["id"]

    # =========================================================================
    # REVIEW + GRANT
    # =========================================================================

    grant_response = client.post(
        f"/api/v1/emergency-access/requests/{emergency_access_id}/grant",
        json={
            "duration_minutes": 20,
            "review_notes": "Approved for immediate emergency treatment.",
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert grant_response.status_code == 200, (
        grant_response.get_json()
    )

    grant_body = grant_response.get_json()

    assert grant_body["success"] is True
    assert (
        grant_body["data"]["status"]
        == EmergencyAccessStatus.ACTIVE.value
    )
    assert (
        grant_body["data"]["reviewed_by_user_id"]
        == admin.id
    )
    assert grant_body["data"]["granted_at"] is not None
    assert grant_body["data"]["expires_at"] is not None

    # =========================================================================
    # BREAK-GLASS ENFORCEMENT BOUNDARY
    # =========================================================================

    assert (
        assert_emergency_access(
            actor_id=doctor_staff.user.id,
            patient_id=patient_id,
            resource_type="patient",
            resource_id=patient_id,
            action="read",
        )
        is True
    )

    assert (
        assert_emergency_access(
            actor_id=doctor_staff.user.id,
            patient_id=patient_id,
            resource_type="patient",
            resource_id=patient_id + 1,
            action="read",
        )
        is False
    )

    assert (
        assert_emergency_access(
            actor_id=doctor_staff.user.id,
            patient_id=patient_id,
            resource_type="patient",
            resource_id=patient_id,
            action="write",
        )
        is False
    )

    # =========================================================================
    # CONSENT GUARD + EMERGENCY EXCEPTION
    # =========================================================================

    consent_evaluation = evaluate_consent_guard(
        actor_id=doctor_staff.user.id,
        patient_id=patient_id,
        clinic_id=clinic.id,
        recipient_role=Role.DOCTOR.value,
        purpose="Emergency clinical care.",
        emergency_exception=True,
        consent_reference=None,
        policy_context={
            "source": "phase8_gate8_e2e",
        },
    )

    assert (
        consent_evaluation.decision
        == ConsentGuardDecision.EMERGENCY_EXCEPTION
    )
    assert (
        consent_evaluation.emergency_exception
        is True
    )
    assert (
        consent_evaluation.emergency_access_id
        == emergency_access_id
    )
    assert (
        consent_evaluation.effective_from
        is not None
    )
    assert (
        consent_evaluation.effective_until
        is not None
    )

    # =========================================================================
    # EMERGENCY ACCESS AUDIT
    # =========================================================================

    db.session.expire_all()

    emergency_audits = (
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type
                == "EmergencyAccessGrant",
                AuditLog.entity_id
                == emergency_access_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    assert emergency_audits

    assert any(
        row.action is AuditAction.CREATE
        and row.user_id == doctor_staff.user.id
        for row in emergency_audits
    )

    assert any(
        row.action is AuditAction.STATUS_CHANGE
        and row.user_id == admin.id
        for row in emergency_audits
    )

    assert any(
        row.action is AuditAction.VIEW
        and row.user_id == doctor_staff.user.id
        for row in emergency_audits
    )

    assert all(
        row.clinic_id == clinic.id
        for row in emergency_audits
    )

    # =========================================================================
    # SECOND-CLINIC PATIENT MUST NOT BE BREAK-GLASS TARGET
    # =========================================================================

    second_clinic = make_clinic(
        name="Gate 8 Other Clinic",
    )

    foreign_patient = make_patient(
        second_clinic,
        first_name="Foreign",
        last_name="Patient",
    )

    foreign_request_response = client.post(
        "/api/v1/emergency-access/requests",
        json={
            "patient_id": foreign_patient.id,
            "reason": "Cross-tenant emergency test.",
            "purpose": "Cross-tenant denial test.",
            "scope": [
                "patient:read",
            ],
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert foreign_request_response.status_code == 404

    # =========================================================================
    # REVOKE + ENFORCEMENT MUST IMMEDIATELY FAIL
    # =========================================================================

    revoke_response = client.post(
        f"/api/v1/emergency-access/requests/{emergency_access_id}/revoke",
        json={
            "reason": "Emergency treatment completed.",
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert revoke_response.status_code == 200, (
        revoke_response.get_json()
    )

    revoke_body = revoke_response.get_json()

    assert revoke_body["success"] is True
    assert (
        revoke_body["data"]["status"]
        == EmergencyAccessStatus.REVOKED.value
    )

    assert (
        assert_emergency_access(
            actor_id=doctor_staff.user.id,
            patient_id=patient_id,
            resource_type="patient",
            resource_id=patient_id,
            action="read",
        )
        is False
    )

    # =========================================================================
    # CLINICAL SAFETY RULE
    # =========================================================================

    drug_a_response = client.post(
        "/api/v1/pharmacy/drugs",
        json={
            "name": "Gate 8 Drug A",
            "generic_name": "Gate 8 Drug A",
            "dosage_form": "tablet",
            "strength": "100 mg",
            "unit_price": "5.00",
            "is_controlled": False,
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert drug_a_response.status_code == 201, (
        drug_a_response.get_json()
    )

    drug_a_id = drug_a_response.get_json()["data"]["id"]

    drug_b_response = client.post(
        "/api/v1/pharmacy/drugs",
        json={
            "name": "Gate 8 Drug B",
            "generic_name": "Gate 8 Drug B",
            "dosage_form": "tablet",
            "strength": "100 mg",
            "unit_price": "5.00",
            "is_controlled": False,
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert drug_b_response.status_code == 201, (
        drug_b_response.get_json()
    )

    drug_b_id = drug_b_response.get_json()["data"]["id"]

    rule_response = client.post(
        "/api/v1/clinical-safety/rules",
        json={
            "rule_code": "GATE8_EMERGENCY_MED_BLOCK",
            "name": "Gate 8 Emergency Medication Block",
            "description": (
                "Break-glass access must never bypass "
                "clinical medication safety."
            ),
            "scope": "clinic",
            "rule_type": "drug_interaction",
            "severity": "critical",
            "action": "block",
            "conditions": {},
            "configuration": {
                "drug_a_id": drug_a_id,
                "drug_b_id": drug_b_id,
                "minimum_severity": "moderate",
            },
            "priority": 1,
            "enabled": True,
        },
        headers={
            "Authorization": (
                f"Bearer {admin_login['access_token']}"
            ),
        },
    )

    assert rule_response.status_code == 201, (
        rule_response.get_json()
    )

    rule_body = rule_response.get_json()

    assert rule_body["rule"]["clinic_id"] == clinic.id
    assert (
        rule_body["rule"]["rule_type"]
        == "drug_interaction"
    )
    assert rule_body["rule"]["action"] == "block"
    assert rule_body["rule"]["enabled"] is True

    # =========================================================================
    # CLINICAL SAFETY ENGINE MUST BLOCK
    # EVEN WHEN EMERGENCY ACCESS CONTEXT EXISTS
    # =========================================================================

    safety_result = evaluate_medication_safety(
        clinic_id=clinic.id,
        medication_ids=[
            drug_a_id,
            drug_b_id,
        ],
        context={
            "patient_id": patient_id,
            "emergency_access_id": emergency_access_id,
            "emergency_exception": True,
            "proposed_medication": {
                "drug_id": drug_b_id,
                "dose": 100,
            },
        },
    )

    assert safety_result.blocked is True
    assert safety_result.outcome == "blocked"

    # =========================================================================
    # REAL PRESCRIPTION WORKFLOW
    #
    # This is the Gate 8 downstream integration assertion.
    # A clinical safety BLOCK must stop prescription creation.
    # =========================================================================

    prescription_response = client.post(
        "/api/v1/prescriptions",
        json={
            "patient_id": patient_id,
            "items": [
                {
                    "drug_id": drug_a_id,
                    "dosage": "100 mg",
                    "frequency": "once daily",
                    "duration": "5 days",
                    "quantity": 5,
                },
                {
                    "drug_id": drug_b_id,
                    "dosage": "100 mg",
                    "frequency": "once daily",
                    "duration": "5 days",
                    "quantity": 5,
                },
            ],
            "notes": (
                "Gate 8 emergency-access clinical-safety "
                "enforcement test."
            ),
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert prescription_response.status_code == 422, (
        "Clinical safety BLOCK must prevent prescription creation. "
        f"Response: {prescription_response.get_json()}"
    )

    assert (
        db.session.execute(
            db.select(Prescription)
            .where(
                Prescription.patient_id == patient_id,
                Prescription.clinic_id == clinic.id,
            )
        )
        .scalars()
        .first()
        is None
    )

    print(
        "PHASE8_E2E_GATE8_EMERGENCY_CLINICAL_SAFETY=PASS"
    )
