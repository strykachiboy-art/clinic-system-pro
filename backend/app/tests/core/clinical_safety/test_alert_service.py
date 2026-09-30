from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.clinical_safety.services.alert_service import (
    acknowledge_clinical_alert,
    build_alert_deduplication_key,
    create_alerts_from_evaluation,
    get_clinical_alert,
    list_clinical_alerts,
    resolve_clinical_alert,
)
from app.core.clinical_safety.services.rule_engine_service import (
    ClinicalSafetyEvaluation,
)
from app.core.clinical_safety.services.rule_evaluator import (
    RuleEvaluationResult,
)
from app.core.enums.clinical_safety_enums import (
    AlertAcknowledgementType,
    ClinicalAlertStatus,
    ClinicalRuleAction,
    ClinicalRuleSeverity,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


def make_result(
    *,
    rule_id=1,
    rule_code="TEST_RULE",
    rule_version=1,
    severity="high",
    action="alert",
    matched=True,
    outcome="warning",
):
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_code=rule_code,
        rule_version=rule_version,
        severity=severity,
        action=action,
        priority=100,
        hard_rule=False,
        matched=matched,
        outcome=outcome,
        reason="Test clinical safety alert",
        evidence={"test": True},
    )


def make_evaluation(
    clinic_id=1,
    *results,
):
    return ClinicalSafetyEvaluation(
        evaluated_at=__import__(
            "datetime"
        ).datetime.now(
            __import__(
                "datetime"
            ).timezone.utc
        ),
        clinic_id=clinic_id,
        department_code=None,
        results=tuple(results),
        outcome=(
            results[-1].outcome
            if results
            else "safe"
        ),
        matched_rule_count=sum(
            result.matched
            for result in results
        ),
    )


class TestBuildAlertDeduplicationKey:
    def test_same_event_produces_same_key(self):
        result = make_result()

        first = build_alert_deduplication_key(
            patient_id=10,
            result=result,
            source_type="prescription",
            source_id=50,
            context={
                "drug_id": 5,
                "dose": 1000,
            },
        )

        second = build_alert_deduplication_key(
            patient_id=10,
            result=result,
            source_type="prescription",
            source_id=50,
            context={
                "dose": 1000,
                "drug_id": 5,
            },
        )

        assert first == second

    def test_different_source_produces_different_key(self):
        result = make_result()

        first = build_alert_deduplication_key(
            patient_id=10,
            result=result,
            source_type="prescription",
            source_id=50,
            context={},
        )

        second = build_alert_deduplication_key(
            patient_id=10,
            result=result,
            source_type="prescription",
            source_id=51,
            context={},
        )

        assert first != second

    def test_different_rule_version_produces_different_key(self):
        first = make_result(
            rule_version=1,
        )
        second = make_result(
            rule_version=2,
        )

        key_one = build_alert_deduplication_key(
            patient_id=10,
            result=first,
            source_type="prescription",
            source_id=50,
            context={},
        )

        key_two = build_alert_deduplication_key(
            patient_id=10,
            result=second,
            source_type="prescription",
            source_id=50,
            context={},
        )

        assert key_one != key_two


class TestCreateAlertsFromEvaluation:
    def test_creates_alert_for_matched_rule(
        self,
        db_session,
        patient,
        clinical_rule,
        clinical_safety_admin,
        clinical_alert_audit_mock,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
            rule_code=clinical_rule.rule_code,
            rule_version=clinical_rule.version,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
            context={
                "drug_ids": [1, 2],
            },
        )

        assert len(alerts) == 1

        alert = alerts[0]

        assert alert.id is not None
        assert alert.clinic_id == patient.clinic_id
        assert alert.patient_id == patient.id
        assert alert.rule_id == clinical_rule.id
        assert alert.rule_version == clinical_rule.version
        assert alert.status == ClinicalAlertStatus.OPEN
        assert alert.source_type == "prescription"
        assert alert.source_id == 100
        assert alert.deduplication_key

        assert clinical_alert_audit_mock.called

    def test_unmatched_results_do_not_create_alerts(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
            matched=False,
            outcome="safe",
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
        )

        assert alerts == []

    def test_duplicate_event_returns_existing_alert(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
            rule_code=clinical_rule.rule_code,
            rule_version=clinical_rule.version,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        first = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
            context={"dose": 1000},
        )

        second = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
            context={"dose": 1000},
        )

        assert first[0].id == second[0].id

    def test_different_context_creates_new_alert(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
            rule_code=clinical_rule.rule_code,
            rule_version=clinical_rule.version,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        first = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
            context={"dose": 1000},
        )

        second = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=100,
            context={"dose": 1500},
        )

        assert first[0].id != second[0].id

    def test_cross_clinic_patient_is_hidden(
        self,
        patient,
        clinical_safety_other_clinic,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            clinical_safety_other_clinic.id,
            result,
        )

        with pytest.raises(
            NotFoundError
        ):
            create_alerts_from_evaluation(
                clinic_id=clinical_safety_other_clinic.id,
                patient_id=patient.id,
                evaluation=evaluation,
                source_type="prescription",
                source_id=1,
            )

    def test_evaluation_clinic_mismatch_is_rejected(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id + 1,
            result,
        )

        with pytest.raises(
            ValidationError
        ):
            create_alerts_from_evaluation(
                clinic_id=patient.clinic_id,
                patient_id=patient.id,
                evaluation=evaluation,
                source_type="prescription",
                source_id=1,
            )


class TestGetAndListClinicalAlerts:
    def test_get_alert_is_tenant_scoped(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=10,
        )

        found = get_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
        )

        assert found.id == alerts[0].id

    def test_cross_clinic_get_is_hidden(
        self,
        patient,
        clinical_rule,
        clinical_safety_other_clinic,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=11,
        )

        with pytest.raises(
            NotFoundError
        ):
            get_clinical_alert(
                clinic_id=clinical_safety_other_clinic.id,
                alert_id=alerts[0].id,
            )

    def test_list_filters_by_patient_and_status(
        self,
        patient,
        clinical_rule,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=12,
        )

        page = list_clinical_alerts(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            status=ClinicalAlertStatus.OPEN,
        )

        assert page["total"] == 1
        assert len(page["items"]) == 1

    def test_pagination_is_deterministic(
        self,
        patient,
        clinical_rule,
    ):
        for source_id in (20, 21, 22):
            result = make_result(
                rule_id=clinical_rule.id,
                rule_code=clinical_rule.rule_code,
                rule_version=clinical_rule.version,
            )

            evaluation = make_evaluation(
                patient.clinic_id,
                result,
            )

            create_alerts_from_evaluation(
                clinic_id=patient.clinic_id,
                patient_id=patient.id,
                evaluation=evaluation,
                source_type="prescription",
                source_id=source_id,
                context={"source": source_id},
            )

        page = list_clinical_alerts(
            clinic_id=patient.clinic_id,
            page=1,
            per_page=2,
        )

        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["page"] == 1
        assert page["per_page"] == 2


class TestResolveClinicalAlert:
    def test_resolve_alert(
        self,
        patient,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=30,
        )

        resolved = resolve_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
            actor_user_id=clinical_safety_admin.id,
        )

        assert resolved.status == ClinicalAlertStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_cross_clinic_resolve_is_hidden(
        self,
        patient,
        clinical_rule,
        clinical_safety_other_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=31,
        )

        with pytest.raises(
            NotFoundError
        ):
            resolve_clinical_alert(
                clinic_id=patient.clinic_id,
                alert_id=alerts[0].id,
                actor_user_id=clinical_safety_other_admin.id,
            )


class TestAcknowledgeClinicalAlert:
    def test_acknowledge_alert(
        self,
        patient,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=40,
        )

        acknowledgement = acknowledge_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
            actor_user_id=clinical_safety_admin.id,
            data={
                "acknowledgement_type": (
                    AlertAcknowledgementType.ACKNOWLEDGED
                ),
            },
        )

        assert acknowledgement.id is not None
        assert (
            acknowledgement.acknowledgement_type
            == AlertAcknowledgementType.ACKNOWLEDGED
        )

        alert = get_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
        )

        assert alert.status == ClinicalAlertStatus.ACKNOWLEDGED

    def test_override_requires_justification(
        self,
        patient,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=41,
        )

        with pytest.raises(
            Exception
        ):
            acknowledge_clinical_alert(
                clinic_id=patient.clinic_id,
                alert_id=alerts[0].id,
                actor_user_id=clinical_safety_admin.id,
                data={
                    "acknowledgement_type": (
                        AlertAcknowledgementType.OVERRIDDEN
                    ),
                },
            )

    def test_override_changes_alert_to_overridden(
        self,
        patient,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=42,
        )

        acknowledgement = acknowledge_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
            actor_user_id=clinical_safety_admin.id,
            data={
                "acknowledgement_type": (
                    AlertAcknowledgementType.OVERRIDDEN
                ),
                "justification": "Clinical benefit outweighs documented risk.",
            },
        )

        assert (
            acknowledgement.acknowledgement_type
            == AlertAcknowledgementType.OVERRIDDEN
        )

        alert = get_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
        )

        assert alert.status == ClinicalAlertStatus.OVERRIDDEN

    def test_critical_hard_rule_cannot_be_overridden(
        self,
        patient,
        clinical_hard_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_hard_rule.id,
            rule_code=clinical_hard_rule.rule_code,
            rule_version=clinical_hard_rule.version,
            severity="critical",
            action="block",
            outcome="blocked",
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=43,
        )

        with pytest.raises(
            ValidationError
        ):
            acknowledge_clinical_alert(
                clinic_id=patient.clinic_id,
                alert_id=alerts[0].id,
                actor_user_id=clinical_safety_admin.id,
                data={
                    "acknowledgement_type": (
                        AlertAcknowledgementType.OVERRIDDEN
                    ),
                    "justification": "Attempted override.",
                },
            )

    def test_duplicate_acknowledgement_is_rejected(
        self,
        patient,
        clinical_rule,
        clinical_safety_admin,
    ):
        result = make_result(
            rule_id=clinical_rule.id,
        )

        evaluation = make_evaluation(
            patient.clinic_id,
            result,
        )

        alerts = create_alerts_from_evaluation(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            evaluation=evaluation,
            source_type="prescription",
            source_id=44,
        )

        data = {
            "acknowledgement_type": (
                AlertAcknowledgementType.ACKNOWLEDGED
            ),
        }

        acknowledge_clinical_alert(
            clinic_id=patient.clinic_id,
            alert_id=alerts[0].id,
            actor_user_id=clinical_safety_admin.id,
            data=data,
        )

        with pytest.raises(
            ConflictError
        ):
            acknowledge_clinical_alert(
                clinic_id=patient.clinic_id,
                alert_id=alerts[0].id,
                actor_user_id=clinical_safety_admin.id,
                data=data,
            )

    def test_invalid_pagination_is_rejected(self):
        with pytest.raises(
            ValidationError
        ):
            list_clinical_alerts(
                clinic_id=1,
                page=0,
            )

        with pytest.raises(
            ValidationError
        ):
            list_clinical_alerts(
                clinic_id=1,
                per_page=501,
            )
