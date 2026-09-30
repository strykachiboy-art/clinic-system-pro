from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from numbers import Real
from typing import Any

from sqlalchemy import func

from app.core.audit.services.audit_service import create_audit_log
from app.core.auth.user.models.user_model import User
from app.core.clinical_safety.models.clinical_rule_model import (
    ClinicalRule,
)
from app.core.clinical_safety.schemas.clinical_rule_schema import (
    ClinicalRuleCreateSchema,
    ClinicalRuleListQuerySchema,
    ClinicalRuleUpdateSchema,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic


SUPPORTED_RULE_MANAGEMENT_ROLES = (
    Role.ADMIN,
    Role.SUPER_ADMIN,
)

MIN_RULE_CODE_LENGTH = 3
MAX_RULE_CODE_LENGTH = 100
MAX_RULE_NAME_LENGTH = 255
MAX_RULE_DESCRIPTION_LENGTH = 5000
MAX_DEPARTMENT_CODE_LENGTH = 100

_ALLOWED_COMPARISON_OPERATORS = {
    "lt",
    "lte",
    "eq",
    "gte",
    "gt",
    "between",
}

_ACTION_ORDER = {
    ClinicalRuleAction.INFORM: 1,
    ClinicalRuleAction.ALERT: 2,
    ClinicalRuleAction.REQUIRE_ACKNOWLEDGEMENT: 3,
    ClinicalRuleAction.REQUIRE_JUSTIFICATION: 4,
    ClinicalRuleAction.BLOCK: 5,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value: Any,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _normalize_optional_text(
    value: str | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    normalized = value.strip()

    return normalized or None


def _validate_actor(
    actor_user_id: int,
) -> User:
    actor_user_id = _validate_positive_id(
        actor_user_id,
        "Actor user ID",
    )

    actor = db.session.get(
        User,
        actor_user_id,
    )

    if actor is None:
        raise NotFoundError(
            f"User {actor_user_id} not found"
        )

    if not actor.is_active:
        raise ValidationError(
            "Authenticated user is inactive"
        )

    if actor.role not in SUPPORTED_RULE_MANAGEMENT_ROLES:
        raise ValidationError(
            "User is not authorized to manage clinical safety rules"
        )

    if (
        actor.role is Role.ADMIN
        and actor.clinic_id is None
    ):
        raise ValidationError(
            "Administrator must belong to a clinic"
        )

    return actor


def _validate_clinic_for_write(
    clinic_id: int,
) -> Clinic:
    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    if clinic.status is not ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic


def _validate_actor_scope(
    *,
    actor: User,
    clinic_id: int | None,
) -> None:
    if actor.role is Role.SUPER_ADMIN:
        return

    if clinic_id is None:
        raise ValidationError(
            "Clinic scope is required for administrator rule management"
        )

    if actor.clinic_id != clinic_id:
        raise NotFoundError(
            "Clinical safety rule not found"
        )


def _require_dict(
    value: Any,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(
            f"{field_name} must be an object"
        )

    return value


def _validate_allowed_keys(
    configuration: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    rule_type: ClinicalRuleType,
) -> None:
    unknown = sorted(
        set(configuration) - allowed
    )

    if unknown:
        raise ValidationError(
            f"{rule_type.value} configuration contains "
            f"unsupported fields: {', '.join(unknown)}"
        )

    missing = sorted(
        required - set(configuration)
    )

    if missing:
        raise ValidationError(
            f"{rule_type.value} configuration is missing "
            f"required fields: {', '.join(missing)}"
        )


def _positive_number(
    value: Any,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be greater than zero"
        )

    return float(value)


def _non_negative_number(
    value: Any,
    field_name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or value < 0
    ):
        raise ValidationError(
            f"{field_name} must be zero or greater"
        )

    return float(value)


def _positive_integer(
    value: Any,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _positive_id_list(
    value: Any,
    field_name: str,
) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValidationError(
            f"{field_name} must be a non-empty list"
        )

    result = []

    for item in value:
        result.append(
            _validate_positive_id(
                item,
                field_name,
            )
        )

    if len(result) != len(set(result)):
        raise ValidationError(
            f"{field_name} must not contain duplicates"
        )

    return result


def _non_empty_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValidationError(
            f"{field_name} must be a non-empty list"
        )

    result = []

    for item in value:
        if not isinstance(item, str):
            raise ValidationError(
                f"{field_name} must contain only strings"
            )

        normalized = item.strip()

        if not normalized:
            raise ValidationError(
                f"{field_name} cannot contain blank values"
            )

        result.append(normalized)

    if len(result) != len(set(result)):
        raise ValidationError(
            f"{field_name} must not contain duplicates"
        )

    return result


def _validate_comparison_rule(
    configuration: dict[str, Any],
    *,
    rule_type: ClinicalRuleType,
) -> None:
    _validate_allowed_keys(
        configuration,
        allowed={
            "measure",
            "operator",
            "threshold",
        },
        required={
            "measure",
            "operator",
            "threshold",
        },
        rule_type=rule_type,
    )

    measure = configuration["measure"]

    if (
        not isinstance(measure, str)
        or not measure.strip()
    ):
        raise ValidationError(
            f"{rule_type.value} measure must be a non-empty string"
        )

    operator = configuration["operator"]

    if operator not in _ALLOWED_COMPARISON_OPERATORS:
        raise ValidationError(
            f"{rule_type.value} operator is invalid"
        )

    threshold = configuration["threshold"]

    if operator == "between":
        if (
            not isinstance(threshold, list)
            or len(threshold) != 2
        ):
            raise ValidationError(
                f"{rule_type.value} between operator "
                "requires exactly two thresholds"
            )

        lower = _non_negative_number(
            threshold[0],
            "Lower threshold",
        )
        upper = _non_negative_number(
            threshold[1],
            "Upper threshold",
        )

        if upper <= lower:
            raise ValidationError(
                f"{rule_type.value} upper threshold "
                "must be greater than lower threshold"
            )

        return

    _non_negative_number(
        threshold,
        "Threshold",
    )


def _validate_rule_configuration(
    *,
    rule_type: ClinicalRuleType,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    configuration = _require_dict(
        configuration,
        "configuration",
    )

    if rule_type is ClinicalRuleType.DRUG_INTERACTION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "drug_a_id",
                "drug_b_id",
                "minimum_severity",
            },
            required={
                "drug_a_id",
                "drug_b_id",
                "minimum_severity",
            },
            rule_type=rule_type,
        )

        drug_a_id = _validate_positive_id(
            configuration["drug_a_id"],
            "drug_a_id",
        )

        drug_b_id = _validate_positive_id(
            configuration["drug_b_id"],
            "drug_b_id",
        )

        if drug_a_id == drug_b_id:
            raise ValidationError(
                "drug_a_id and drug_b_id must be different"
            )

        minimum_severity = configuration[
            "minimum_severity"
        ]

        try:
            ClinicalRuleSeverity(
                minimum_severity
            )
        except ValueError as exc:
            raise ValidationError(
                "minimum_severity is invalid"
            ) from exc

        normalized = dict(configuration)
        normalized["drug_a_id"] = drug_a_id
        normalized["drug_b_id"] = drug_b_id
        normalized["minimum_severity"] = (
            ClinicalRuleSeverity(
                minimum_severity
            ).value
        )

        return normalized

    if rule_type is ClinicalRuleType.ALLERGY_CONFLICT:
        _validate_allowed_keys(
            configuration,
            allowed={
                "allergen",
                "drug_id",
            },
            required={
                "allergen",
            },
            rule_type=rule_type,
        )

        allergen = configuration["allergen"]

        if (
            not isinstance(allergen, str)
            or not allergen.strip()
        ):
            raise ValidationError(
                "allergen must be a non-empty string"
            )

        normalized = dict(configuration)
        normalized["allergen"] = allergen.strip()

        if "drug_id" in normalized:
            normalized["drug_id"] = _validate_positive_id(
                normalized["drug_id"],
                "drug_id",
            )

        return normalized

    if rule_type is ClinicalRuleType.CONTRAINDICATION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "contraindication_codes",
            },
            required={
                "contraindication_codes",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)
        normalized["contraindication_codes"] = (
            _non_empty_string_list(
                normalized["contraindication_codes"],
                "contraindication_codes",
            )
        )

        return normalized

    if rule_type in (
        ClinicalRuleType.MAX_DOSE,
        ClinicalRuleType.MIN_DOSE,
    ):
        _validate_allowed_keys(
            configuration,
            allowed={
                "drug_id",
                "threshold",
                "unit",
                "frequency",
            },
            required={
                "drug_id",
                "threshold",
                "unit",
                "frequency",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)

        normalized["drug_id"] = _validate_positive_id(
            normalized["drug_id"],
            "drug_id",
        )

        normalized["threshold"] = _positive_number(
            normalized["threshold"],
            "threshold",
        )

        if (
            not isinstance(normalized["unit"], str)
            or not normalized["unit"].strip()
        ):
            raise ValidationError(
                "unit must be a non-empty string"
            )

        if (
            not isinstance(normalized["frequency"], str)
            or not normalized["frequency"].strip()
        ):
            raise ValidationError(
                "frequency must be a non-empty string"
            )

        normalized["unit"] = (
            normalized["unit"].strip()
        )
        normalized["frequency"] = (
            normalized["frequency"].strip()
        )

        return normalized

    if rule_type is ClinicalRuleType.AGE_RESTRICTION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "minimum_age",
                "maximum_age",
            },
            required=set(),
            rule_type=rule_type,
        )

        if not configuration:
            raise ValidationError(
                "AGE_RESTRICTION requires at least one age boundary"
            )

        normalized = dict(configuration)

        if "minimum_age" in normalized:
            normalized["minimum_age"] = _non_negative_number(
                normalized["minimum_age"],
                "minimum_age",
            )

        if "maximum_age" in normalized:
            normalized["maximum_age"] = _non_negative_number(
                normalized["maximum_age"],
                "maximum_age",
            )

        if (
            "minimum_age" in normalized
            and "maximum_age" in normalized
            and normalized["maximum_age"]
            < normalized["minimum_age"]
        ):
            raise ValidationError(
                "maximum_age cannot be less than minimum_age"
            )

        return normalized

    if rule_type is ClinicalRuleType.WEIGHT_RESTRICTION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "minimum_weight_kg",
                "maximum_weight_kg",
            },
            required=set(),
            rule_type=rule_type,
        )

        if not configuration:
            raise ValidationError(
                "WEIGHT_RESTRICTION requires at least one weight boundary"
            )

        normalized = dict(configuration)

        if "minimum_weight_kg" in normalized:
            normalized["minimum_weight_kg"] = _positive_number(
                normalized["minimum_weight_kg"],
                "minimum_weight_kg",
            )

        if "maximum_weight_kg" in normalized:
            normalized["maximum_weight_kg"] = _positive_number(
                normalized["maximum_weight_kg"],
                "maximum_weight_kg",
            )

        if (
            "minimum_weight_kg" in normalized
            and "maximum_weight_kg" in normalized
            and normalized["maximum_weight_kg"]
            < normalized["minimum_weight_kg"]
        ):
            raise ValidationError(
                "maximum_weight_kg cannot be less than minimum_weight_kg"
            )

        return normalized

    if rule_type is ClinicalRuleType.PREGNANCY_RESTRICTION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "restricted_statuses",
            },
            required={
                "restricted_statuses",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)
        normalized["restricted_statuses"] = (
            _non_empty_string_list(
                normalized["restricted_statuses"],
                "restricted_statuses",
            )
        )

        return normalized

    if rule_type in (
        ClinicalRuleType.DUPLICATE_THERAPY,
        ClinicalRuleType.THERAPEUTIC_DUPLICATION,
    ):
        _validate_allowed_keys(
            configuration,
            allowed={
                "therapy_group",
                "drug_ids",
            },
            required=set(),
            rule_type=rule_type,
        )

        if (
            "therapy_group" not in configuration
            and "drug_ids" not in configuration
        ):
            raise ValidationError(
                f"{rule_type.value} requires therapy_group or drug_ids"
            )

        normalized = dict(configuration)

        if "therapy_group" in normalized:
            if (
                not isinstance(
                    normalized["therapy_group"],
                    str,
                )
                or not normalized["therapy_group"].strip()
            ):
                raise ValidationError(
                    "therapy_group must be a non-empty string"
                )

            normalized["therapy_group"] = (
                normalized["therapy_group"].strip()
            )

        if "drug_ids" in normalized:
            normalized["drug_ids"] = _positive_id_list(
                normalized["drug_ids"],
                "drug_ids",
            )

        return normalized

    if rule_type in (
        ClinicalRuleType.LAB_CONFLICT,
        ClinicalRuleType.RENAL_FUNCTION,
        ClinicalRuleType.HEPATIC_FUNCTION,
    ):
        _validate_comparison_rule(
            configuration,
            rule_type=rule_type,
        )

        return dict(configuration)

    if rule_type is ClinicalRuleType.DIAGNOSIS_CONFLICT:
        _validate_allowed_keys(
            configuration,
            allowed={
                "diagnosis_codes",
            },
            required={
                "diagnosis_codes",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)
        normalized["diagnosis_codes"] = (
            _non_empty_string_list(
                normalized["diagnosis_codes"],
                "diagnosis_codes",
            )
        )

        return normalized

    if rule_type is ClinicalRuleType.FREQUENCY_LIMIT:
        _validate_allowed_keys(
            configuration,
            allowed={
                "max_occurrences",
                "interval_hours",
            },
            required={
                "max_occurrences",
                "interval_hours",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)

        normalized["max_occurrences"] = _positive_integer(
            normalized["max_occurrences"],
            "max_occurrences",
        )

        normalized["interval_hours"] = _positive_integer(
            normalized["interval_hours"],
            "interval_hours",
        )

        return normalized

    if rule_type is ClinicalRuleType.DURATION_LIMIT:
        _validate_allowed_keys(
            configuration,
            allowed={
                "maximum_days",
            },
            required={
                "maximum_days",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)

        normalized["maximum_days"] = _positive_integer(
            normalized["maximum_days"],
            "maximum_days",
        )

        return normalized

    if rule_type is ClinicalRuleType.PATIENT_SPECIFIC_RESTRICTION:
        _validate_allowed_keys(
            configuration,
            allowed={
                "field",
                "operator",
                "value",
            },
            required={
                "field",
                "operator",
                "value",
            },
            rule_type=rule_type,
        )

        normalized = dict(configuration)

        if (
            not isinstance(
                normalized["field"],
                str,
            )
            or not normalized["field"].strip()
        ):
            raise ValidationError(
                "field must be a non-empty string"
            )

        operator = normalized["operator"]

        if operator not in {
            "eq",
            "ne",
            "in",
            "not_in",
            "lt",
            "lte",
            "gt",
            "gte",
        }:
            raise ValidationError(
                "PATIENT_SPECIFIC_RESTRICTION operator is invalid"
            )

        normalized["field"] = (
            normalized["field"].strip()
        )

        return normalized

    raise ValidationError(
        f"Unsupported clinical rule type '{rule_type.value}'"
    )


def _validate_conditions(
    conditions: Any,
) -> dict[str, Any]:
    conditions = _require_dict(
        conditions,
        "conditions",
    )

    return dict(conditions)


def _validate_rule_scope(
    *,
    actor: User,
    scope: ClinicalRuleScope,
    clinic_id: int | None,
    department_code: str | None,
) -> None:
    if scope is ClinicalRuleScope.GLOBAL:
        if clinic_id is not None:
            raise ValidationError(
                "Global rules cannot belong to a clinic"
            )

        if actor.role is not Role.SUPER_ADMIN:
            raise ValidationError(
                "Only a super administrator can manage global rules"
            )

        if department_code is not None:
            raise ValidationError(
                "Global rules cannot use department_code"
            )

        return

    if clinic_id is None:
        raise ValidationError(
            "Clinic ID is required for clinic and department rules"
        )

    if (
        scope is ClinicalRuleScope.DEPARTMENT
        and not department_code
    ):
        raise ValidationError(
            "department_code is required for department rules"
        )

    if (
        scope is not ClinicalRuleScope.DEPARTMENT
        and department_code is not None
    ):
        raise ValidationError(
            "department_code is only valid for department rules"
        )

    _validate_actor_scope(
        actor=actor,
        clinic_id=clinic_id,
    )


def _validate_hard_rule_policy(
    *,
    actor: User,
    scope: ClinicalRuleScope,
    action: ClinicalRuleAction,
    is_hard_rule: bool,
) -> None:
    if not is_hard_rule:
        return

    if actor.role is not Role.SUPER_ADMIN:
        raise ValidationError(
            "Only a super administrator can create or modify hard safety rules"
        )

    if scope is not ClinicalRuleScope.GLOBAL:
        raise ValidationError(
            "Hard safety rules must be global"
        )

    if action is not ClinicalRuleAction.BLOCK:
        raise ValidationError(
            "Hard safety rules must use BLOCK action"
        )


def _validate_effective_window(
    *,
    effective_from: datetime,
    effective_until: datetime | None,
) -> None:
    if (
        effective_from.tzinfo is None
        or effective_from.utcoffset() is None
    ):
        raise ValidationError(
            "effective_from must include timezone information"
        )

    if effective_until is not None:
        if (
            effective_until.tzinfo is None
            or effective_until.utcoffset() is None
        ):
            raise ValidationError(
                "effective_until must include timezone information"
            )

        if effective_until <= effective_from:
            raise ValidationError(
                "effective_until must be later than effective_from"
            )


def _get_rule(
    rule_id: int,
    *,
    for_update: bool = False,
) -> ClinicalRule:
    rule_id = _validate_positive_id(
        rule_id,
        "Clinical rule ID",
    )

    statement = db.select(
        ClinicalRule
    ).where(
        ClinicalRule.id == rule_id
    )

    if for_update:
        statement = statement.with_for_update()

    rule = db.session.execute(
        statement
    ).scalar_one_or_none()

    if rule is None:
        raise NotFoundError(
            f"Clinical rule {rule_id} not found"
        )

    return rule


def _validate_rule_visibility(
    *,
    actor: User,
    rule: ClinicalRule,
) -> None:
    if rule.scope is ClinicalRuleScope.GLOBAL:
        return

    if actor.role is Role.SUPER_ADMIN:
        return

    if (
        actor.clinic_id is None
        or rule.clinic_id != actor.clinic_id
    ):
        raise NotFoundError(
            "Clinical rule not found"
        )


def _get_latest_rule_version(
    *,
    rule_code: str,
    clinic_id: int | None,
) -> ClinicalRule | None:
    statement = db.select(
        ClinicalRule
    ).where(
        ClinicalRule.rule_code == rule_code,
    )

    if clinic_id is None:
        statement = statement.where(
            ClinicalRule.clinic_id.is_(None)
        )
    else:
        statement = statement.where(
            ClinicalRule.clinic_id == clinic_id
        )

    return db.session.execute(
        statement.order_by(
            ClinicalRule.version.desc(),
            ClinicalRule.id.desc(),
        ).limit(1)
    ).scalar_one_or_none()


def _next_version(
    *,
    rule_code: str,
    clinic_id: int | None,
) -> int:
    statement = db.select(
        func.max(
            ClinicalRule.version
        )
    ).where(
        ClinicalRule.rule_code == rule_code,
    )

    if clinic_id is None:
        statement = statement.where(
            ClinicalRule.clinic_id.is_(None)
        )
    else:
        statement = statement.where(
            ClinicalRule.clinic_id == clinic_id
        )

    current = db.session.execute(
        statement
    ).scalar_one()

    return int(current or 0) + 1


def _serialize_audit_value(
    value: Any,
) -> Any:
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def _rule_audit_value(
    rule: ClinicalRule,
) -> dict[str, Any]:
    return {
        "id": rule.id,
        "clinic_id": rule.clinic_id,
        "rule_code": rule.rule_code,
        "version": rule.version,
        "scope": _serialize_audit_value(
            rule.scope
        ),
        "rule_type": _serialize_audit_value(
            rule.rule_type
        ),
        "severity": _serialize_audit_value(
            rule.severity
        ),
        "action": _serialize_audit_value(
            rule.action
        ),
        "enabled": rule.enabled,
        "is_hard_rule": rule.is_hard_rule,
        "priority": rule.priority,
        "effective_from": (
            rule.effective_from.isoformat()
            if rule.effective_from
            else None
        ),
        "effective_until": (
            rule.effective_until.isoformat()
            if rule.effective_until
            else None
        ),
        "conditions": rule.conditions,
        "configuration": rule.configuration,
        "department_code": rule.department_code,
    }


def get_clinical_rule(
    *,
    actor_user_id: int,
    rule_id: int,
) -> ClinicalRule:
    actor = _validate_actor(
        actor_user_id
    )

    rule = _get_rule(
        rule_id
    )

    _validate_rule_visibility(
        actor=actor,
        rule=rule,
    )

    return rule


def list_clinical_rules(
    *,
    actor_user_id: int,
    clinic_id: int | None = None,
    query: ClinicalRuleListQuerySchema | dict | None = None,
) -> dict[str, Any]:
    actor = _validate_actor(
        actor_user_id
    )

    if query is None:
        query = ClinicalRuleListQuerySchema()
    elif isinstance(query, dict):
        query = ClinicalRuleListQuerySchema.model_validate(
            query
        )

    if actor.role is Role.ADMIN:
        clinic_id = actor.clinic_id

    elif clinic_id is not None:
        clinic_id = _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

    statement = db.select(
        ClinicalRule
    )

    if actor.role is not Role.SUPER_ADMIN:
        conditions = [
            ClinicalRule.clinic_id == clinic_id,
        ]

        if query.include_global:
            conditions = [
                db.or_(
                    ClinicalRule.clinic_id == clinic_id,
                    ClinicalRule.clinic_id.is_(None),
                )
            ]

        statement = statement.where(
            *conditions
        )

    elif clinic_id is not None:
        _validate_clinic_for_write(
            clinic_id
        )

        if query.include_global:
            statement = statement.where(
                db.or_(
                    ClinicalRule.clinic_id == clinic_id,
                    ClinicalRule.clinic_id.is_(None),
                )
            )
        else:
            statement = statement.where(
                ClinicalRule.clinic_id == clinic_id
            )

    if query.rule_type is not None:
        statement = statement.where(
            ClinicalRule.rule_type == query.rule_type
        )

    if query.scope is not None:
        statement = statement.where(
            ClinicalRule.scope == query.scope
        )

    if query.severity is not None:
        statement = statement.where(
            ClinicalRule.severity == query.severity
        )

    if query.action is not None:
        statement = statement.where(
            ClinicalRule.action == query.action
        )

    if query.enabled is not None:
        statement = statement.where(
            ClinicalRule.enabled == query.enabled
        )

    if query.department_code is not None:
        statement = statement.where(
            ClinicalRule.department_code
            == query.department_code
        )

    count = db.session.execute(
        db.select(
            func.count()
        ).select_from(
            statement.subquery()
        )
    ).scalar_one()

    offset = (
        (query.page - 1)
        * query.per_page
    )

    items = list(
        db.session.execute(
            statement
            .order_by(
                ClinicalRule.priority.asc(),
                ClinicalRule.rule_code.asc(),
                ClinicalRule.version.desc(),
                ClinicalRule.id.desc(),
            )
            .offset(offset)
            .limit(query.per_page)
        ).scalars()
    )

    return {
        "items": items,
        "total": count,
        "page": query.page,
        "per_page": query.per_page,
    }


@transactional
def create_clinical_rule(
    *,
    actor_user_id: int,
    data: ClinicalRuleCreateSchema | dict,
    clinic_id: int | None = None,
    is_hard_rule: bool = False,
) -> ClinicalRule:
    actor = _validate_actor(
        actor_user_id
    )

    if isinstance(data, dict):
        data = ClinicalRuleCreateSchema.model_validate(
            data
        )

    if (
        actor.role is Role.ADMIN
        and clinic_id is None
    ):
        clinic_id = actor.clinic_id

    if clinic_id is not None:
        clinic_id = _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )

    if (
        clinic_id is not None
        and actor.role is Role.ADMIN
    ):
        _validate_clinic_for_write(
            clinic_id
        )

    _validate_rule_scope(
        actor=actor,
        scope=data.scope,
        clinic_id=clinic_id,
        department_code=data.department_code,
    )

    if data.scope is not ClinicalRuleScope.GLOBAL:
        _validate_clinic_for_write(
            clinic_id
        )

    _validate_hard_rule_policy(
        actor=actor,
        scope=data.scope,
        action=data.action,
        is_hard_rule=is_hard_rule,
    )

    configuration = _validate_rule_configuration(
        rule_type=data.rule_type,
        configuration=data.configuration,
    )

    conditions = _validate_conditions(
        data.conditions
    )

    effective_from = data.effective_from.astimezone(
        timezone.utc
    )

    effective_until = (
        data.effective_until.astimezone(
            timezone.utc
        )
        if data.effective_until is not None
        else None
    )

    _validate_effective_window(
        effective_from=effective_from,
        effective_until=effective_until,
    )

    latest = _get_latest_rule_version(
        rule_code=data.rule_code,
        clinic_id=clinic_id,
    )

    version = _next_version(
        rule_code=data.rule_code,
        clinic_id=clinic_id,
    )

    if latest is not None:
        if effective_from <= latest.effective_from:
            raise ConflictError(
                "A newer clinical rule version already exists"
            )

        if (
            latest.effective_until is not None
            and effective_from
            <= latest.effective_until
        ):
            raise ConflictError(
                "The new clinical rule version overlaps "
                "the existing effective window"
            )

        if latest.effective_until is None:
            latest.effective_until = (
                effective_from
                - timedelta(microseconds=1)
            )

        db.session.flush()

    rule = ClinicalRule(
        clinic_id=clinic_id,
        rule_code=data.rule_code,
        name=data.name,
        description=data.description,
        scope=data.scope,
        rule_type=data.rule_type,
        severity=data.severity,
        action=data.action,
        conditions=conditions,
        configuration=configuration,
        department_code=data.department_code,
        priority=data.priority,
        enabled=data.enabled,
        is_hard_rule=is_hard_rule,
        version=version,
        effective_from=effective_from,
        effective_until=effective_until,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )

    db.session.add(
        rule
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="ClinicalRule",
        entity_id=rule.id,
        user_id=actor.id,
        description=(
            f"Clinical safety rule '{rule.rule_code}' "
            f"version {rule.version} created"
        ),
        new_value=_rule_audit_value(
            rule
        ),
    )

    return rule


@transactional
def update_clinical_rule(
    *,
    actor_user_id: int,
    rule_id: int,
    data: ClinicalRuleUpdateSchema | dict,
) -> ClinicalRule:
    actor = _validate_actor(
        actor_user_id
    )

    if isinstance(data, dict):
        data = ClinicalRuleUpdateSchema.model_validate(
            data
        )

    current = _get_rule(
        rule_id,
        for_update=True,
    )

    _validate_rule_visibility(
        actor=actor,
        rule=current,
    )

    if current.scope is ClinicalRuleScope.GLOBAL:
        if actor.role is not Role.SUPER_ADMIN:
            raise NotFoundError(
                "Clinical rule not found"
            )

    else:
        _validate_actor_scope(
            actor=actor,
            clinic_id=current.clinic_id,
        )

        _validate_clinic_for_write(
            current.clinic_id
        )

    latest = _get_latest_rule_version(
        rule_code=current.rule_code,
        clinic_id=current.clinic_id,
    )

    if latest is None:
        raise ValidationError(
            "Clinical rule version history is inconsistent"
        )

    if latest.id != current.id:
        raise ConflictError(
            "Only the latest clinical rule version can be updated"
        )

    updates = data.model_dump(
        exclude_unset=True
    )

    if not updates:
        raise ValidationError(
            "No fields provided for update"
        )

    effective_from = (
        data.effective_from.astimezone(
            timezone.utc
        )
        if data.effective_from is not None
        else _utcnow()
    )

    effective_until = (
        data.effective_until.astimezone(
            timezone.utc
        )
        if data.effective_until is not None
        else None
    )

    if effective_from <= current.effective_from:
        raise ConflictError(
            "New rule version must start after the current version"
        )

    _validate_effective_window(
        effective_from=effective_from,
        effective_until=effective_until,
    )

    next_severity = (
        data.severity
        if data.severity is not None
        else current.severity
    )

    next_action = (
        data.action
        if data.action is not None
        else current.action
    )

    next_configuration = (
        data.configuration
        if data.configuration is not None
        else current.configuration
    )

    next_rule_type = current.rule_type

    if current.is_hard_rule:
        _validate_hard_rule_policy(
            actor=actor,
            scope=current.scope,
            action=next_action,
            is_hard_rule=True,
        )

    configuration = _validate_rule_configuration(
        rule_type=next_rule_type,
        configuration=next_configuration,
    )

    conditions = (
        data.conditions
        if data.conditions is not None
        else current.conditions
    )

    conditions = _validate_conditions(
        conditions
    )

    department_code = (
        data.department_code
        if data.department_code is not None
        else current.department_code
    )

    name = (
        data.name
        if data.name is not None
        else current.name
    )

    description = (
        data.description
        if data.description is not None
        else current.description
    )

    priority = (
        data.priority
        if data.priority is not None
        else current.priority
    )

    enabled = (
        data.enabled
        if data.enabled is not None
        else current.enabled
    )

    if (
        current.scope is ClinicalRuleScope.DEPARTMENT
        and not department_code
    ):
        raise ValidationError(
            "department_code is required for department rules"
        )

    if (
        current.scope is not ClinicalRuleScope.DEPARTMENT
        and department_code is not None
    ):
        raise ValidationError(
            "department_code is only valid for department rules"
        )

    version = current.version + 1

    current.effective_until = (
        effective_from
        - timedelta(microseconds=1)
    )

    db.session.flush()

    next_rule = ClinicalRule(
        clinic_id=current.clinic_id,
        rule_code=current.rule_code,
        name=name,
        description=description,
        scope=current.scope,
        rule_type=next_rule_type,
        severity=next_severity,
        action=next_action,
        conditions=conditions,
        configuration=configuration,
        department_code=department_code,
        priority=priority,
        enabled=enabled,
        is_hard_rule=current.is_hard_rule,
        version=version,
        effective_from=effective_from,
        effective_until=effective_until,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )

    db.session.add(
        next_rule
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="ClinicalRule",
        entity_id=next_rule.id,
        user_id=actor.id,
        description=(
            f"Clinical safety rule '{next_rule.rule_code}' "
            f"version {next_rule.version} created from "
            f"version {current.version}"
        ),
        old_value=_rule_audit_value(
            current
        ),
        new_value=_rule_audit_value(
            next_rule
        ),
    )

    return next_rule


@transactional
def disable_clinical_rule(
    *,
    actor_user_id: int,
    rule_id: int,
) -> ClinicalRule:
    return update_clinical_rule(
        actor_user_id=actor_user_id,
        rule_id=rule_id,
        data=ClinicalRuleUpdateSchema(
            enabled=False,
        ),
    )