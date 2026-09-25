from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import and_, or_

from app.core.clinical_safety.models.clinical_rule_model import ClinicalRule
from app.core.clinical_safety.services.rule_evaluator import (
    OUTCOME_ACKNOWLEDGEMENT_REQUIRED,
    OUTCOME_BLOCKED,
    OUTCOME_INFORMATION,
    OUTCOME_JUSTIFICATION_REQUIRED,
    OUTCOME_SAFE,
    OUTCOME_WARNING,
    RuleEvaluationResult,
    evaluate_rule,
)
from app.core.enums.clinical_safety_enums import ClinicalRuleScope
from app.core.exceptions import ValidationError
from app.extensions import db


_OUTCOME_RANK = {
    OUTCOME_SAFE: 0,
    OUTCOME_INFORMATION: 1,
    OUTCOME_WARNING: 2,
    OUTCOME_ACKNOWLEDGEMENT_REQUIRED: 3,
    OUTCOME_JUSTIFICATION_REQUIRED: 4,
    OUTCOME_BLOCKED: 5,
}

_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "moderate": 2,
    "low": 3,
    "info": 4,
}


@dataclass(frozen=True)
class ClinicalSafetyEvaluation:
    evaluated_at: datetime
    clinic_id: int
    department_code: str | None
    results: tuple[RuleEvaluationResult, ...]
    outcome: str
    matched_rule_count: int

    @property
    def blocked(self) -> bool:
        return self.outcome == OUTCOME_BLOCKED

    @property
    def requires_acknowledgement(self) -> bool:
        return (
            self.outcome
            == OUTCOME_ACKNOWLEDGEMENT_REQUIRED
        )

    @property
    def requires_justification(self) -> bool:
        return (
            self.outcome
            == OUTCOME_JUSTIFICATION_REQUIRED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated_at": self.evaluated_at.isoformat(),
            "clinic_id": self.clinic_id,
            "department_code": self.department_code,
            "outcome": self.outcome,
            "matched_rule_count": self.matched_rule_count,
            "blocked": self.blocked,
            "requires_acknowledgement": (
                self.requires_acknowledgement
            ),
            "requires_justification": (
                self.requires_justification
            ),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_evaluation_time(
    value: datetime | None,
) -> datetime:
    if value is None:
        return _utcnow()

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(
            "Evaluation time must be timezone-aware"
        )

    return value.astimezone(timezone.utc)


def _validate_clinic_id(
    clinic_id: int,
) -> None:
    if (
        isinstance(clinic_id, bool)
        or not isinstance(clinic_id, int)
        or clinic_id <= 0
    ):
        raise ValidationError(
            "Clinic ID must be a positive integer"
        )


def _normalize_department_code(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            "Department code must be a string"
        )

    value = value.strip().upper()

    return value or None


def resolve_clinical_rules(
    *,
    clinic_id: int,
    department_code: str | None = None,
    evaluation_at: datetime | None = None,
) -> list[ClinicalRule]:
    _validate_clinic_id(clinic_id)

    evaluation_at = _normalize_evaluation_time(
        evaluation_at
    )

    department_code = _normalize_department_code(
        department_code
    )

    scope_filter = or_(
        ClinicalRule.scope
        == ClinicalRuleScope.GLOBAL,
        and_(
            ClinicalRule.scope
            == ClinicalRuleScope.CLINIC,
            ClinicalRule.clinic_id == clinic_id,
        ),
        and_(
            ClinicalRule.scope
            == ClinicalRuleScope.DEPARTMENT,
            ClinicalRule.clinic_id == clinic_id,
            ClinicalRule.department_code
            == department_code,
        ),
    )

    statement = (
        db.select(ClinicalRule)
        .where(
            ClinicalRule.enabled.is_(True),
            ClinicalRule.effective_from
            <= evaluation_at,
            or_(
                ClinicalRule.effective_until.is_(None),
                ClinicalRule.effective_until
                >= evaluation_at,
            ),
            scope_filter,
        )
        .order_by(
            ClinicalRule.priority.asc(),
            ClinicalRule.rule_code.asc(),
            ClinicalRule.version.desc(),
            ClinicalRule.id.asc(),
        )
    )

    rules = db.session.execute(
        statement
    ).scalars().all()

    return list(rules)


def _result_sort_key(
    result: RuleEvaluationResult,
) -> tuple[int, int, str, int, int]:
    severity_rank = _SEVERITY_RANK.get(
        result.severity,
        len(_SEVERITY_RANK),
    )

    return (
        severity_rank,
        result.priority,
        result.rule_code,
        result.rule_id,
        result.rule_version,
    )


def _aggregate_outcome(
    results: list[RuleEvaluationResult],
) -> str:
    if not results:
        return OUTCOME_SAFE

    return max(
        (
            result.outcome
            for result in results
        ),
        key=lambda outcome: _OUTCOME_RANK.get(
            outcome,
            -1,
        ),
    )


def evaluate_clinical_rules(
    *,
    clinic_id: int,
    context: Mapping[str, Any],
    department_code: str | None = None,
    evaluation_at: datetime | None = None,
    rules: list[ClinicalRule] | None = None,
) -> ClinicalSafetyEvaluation:
    _validate_clinic_id(clinic_id)

    if not isinstance(context, Mapping):
        raise ValidationError(
            "Clinical evaluation context must be an object"
        )

    evaluated_at = _normalize_evaluation_time(
        evaluation_at
    )

    department_code = _normalize_department_code(
        department_code
    )

    resolved_rules = (
        list(rules)
        if rules is not None
        else resolve_clinical_rules(
            clinic_id=clinic_id,
            department_code=department_code,
            evaluation_at=evaluated_at,
        )
    )

    results = [
        evaluate_rule(
            rule,
            context,
        )
        for rule in resolved_rules
    ]

    results.sort(
        key=_result_sort_key
    )

    matched_results = [
        result
        for result in results
        if result.matched
    ]

    return ClinicalSafetyEvaluation(
        evaluated_at=evaluated_at,
        clinic_id=clinic_id,
        department_code=department_code,
        results=tuple(results),
        outcome=_aggregate_outcome(
            matched_results
        ),
        matched_rule_count=len(
            matched_results
        ),
    )