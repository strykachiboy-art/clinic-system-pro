from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicalRule(db.Model):
    __tablename__ = "clinical_rules"

    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "rule_code",
            "version",
            name="uq_clinical_rules_clinic_code_version",
        ),
        CheckConstraint(
            "length(trim(rule_code)) > 0",
            name="ck_clinical_rules_rule_code_nonempty",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_clinical_rules_name_nonempty",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_clinical_rules_version_positive",
        ),
        CheckConstraint(
            "priority >= 0",
            name="ck_clinical_rules_priority_nonnegative",
        ),
        CheckConstraint(
            "effective_until IS NULL "
            "OR effective_until > effective_from",
            name="ck_clinical_rules_valid_effective_window",
        ),
        Index(
            "ix_clinical_rules_clinic_type_enabled",
            "clinic_id",
            "rule_type",
            "enabled",
            "priority",
        ),
        Index(
            "ix_clinical_rules_clinic_effective",
            "clinic_id",
            "effective_from",
            "effective_until",
            "version",
        ),
        Index(
            "ix_clinical_rules_code_scope",
            "rule_code",
            "scope",
            "version",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
        index=True,
    )

    rule_code = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.String(255),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    scope = db.Column(
        db.Enum(ClinicalRuleScope),
        nullable=False,
        default=ClinicalRuleScope.GLOBAL,
        index=True,
    )

    rule_type = db.Column(
        db.Enum(ClinicalRuleType),
        nullable=False,
        index=True,
    )

    severity = db.Column(
        db.Enum(ClinicalRuleSeverity),
        nullable=False,
        index=True,
    )

    action = db.Column(
        db.Enum(ClinicalRuleAction),
        nullable=False,
        index=True,
    )

    conditions = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    configuration = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    department_code = db.Column(
        db.String(100),
        nullable=True,
        index=True,
    )

    priority = db.Column(
        db.Integer,
        nullable=False,
        default=100,
    )

    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    is_hard_rule = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    effective_from = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    effective_until = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<ClinicalRule {self.rule_code} "
            f"v{self.version} "
            f"({self.rule_type.value})>"
        )