"""add clinical safety tables

Revision ID: 70388a132ec2
Revises: b3a237f3f8b7
Create Date: 2026-09-25 15:55:46.315863

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "70388a132ec2"
down_revision = "b3a237f3f8b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clinical_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=True),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scope",
            sa.Enum(
                "GLOBAL",
                "CLINIC",
                "DEPARTMENT",
                name="clinicalrulescope",
            ),
            nullable=False,
        ),
        sa.Column(
            "rule_type",
            sa.Enum(
                "DRUG_INTERACTION",
                "ALLERGY_CONFLICT",
                "CONTRAINDICATION",
                "MAX_DOSE",
                "MIN_DOSE",
                "AGE_RESTRICTION",
                "WEIGHT_RESTRICTION",
                "PREGNANCY_RESTRICTION",
                "DUPLICATE_THERAPY",
                "THERAPEUTIC_DUPLICATION",
                "LAB_CONFLICT",
                "RENAL_FUNCTION",
                "HEPATIC_FUNCTION",
                "DIAGNOSIS_CONFLICT",
                "FREQUENCY_LIMIT",
                "DURATION_LIMIT",
                "PATIENT_SPECIFIC_RESTRICTION",
                name="clinicalruletype",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "INFO",
                "LOW",
                "MODERATE",
                "HIGH",
                "CRITICAL",
                name="clinicalruleseverity",
            ),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum(
                "INFORM",
                "ALERT",
                "REQUIRE_ACKNOWLEDGEMENT",
                "REQUIRE_JUSTIFICATION",
                "BLOCK",
                name="clinicalruleaction",
            ),
            nullable=False,
        ),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("department_code", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_hard_rule", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "effective_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_clinical_rules_valid_effective_window",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_clinical_rules_name_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(rule_code)) > 0",
            name="ck_clinical_rules_rule_code_nonempty",
        ),
        sa.CheckConstraint(
            "priority >= 0",
            name="ck_clinical_rules_priority_nonnegative",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_clinical_rules_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clinic_id",
            "rule_code",
            "version",
            name="uq_clinical_rules_clinic_code_version",
        ),
    )

    with op.batch_alter_table("clinical_rules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_action"),
            ["action"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_rules_clinic_effective",
            ["clinic_id", "effective_from", "effective_until", "version"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_rules_clinic_type_enabled",
            ["clinic_id", "rule_type", "enabled", "priority"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_rules_code_scope",
            ["rule_code", "scope", "version"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_department_code"),
            ["department_code"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_effective_until"),
            ["effective_until"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_enabled"),
            ["enabled"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_is_hard_rule"),
            ["is_hard_rule"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_rule_code"),
            ["rule_code"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_rule_type"),
            ["rule_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_scope"),
            ["scope"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_severity"),
            ["severity"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_rules_updated_by_user_id"),
            ["updated_by_user_id"],
            unique=False,
        )

    op.create_table(
        "clinical_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "INFO",
                "LOW",
                "MODERATE",
                "HIGH",
                "CRITICAL",
                name="clinicalruleseverity",
            ),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum(
                "INFORM",
                "ALERT",
                "REQUIRE_ACKNOWLEDGEMENT",
                "REQUIRE_JUSTIFICATION",
                "BLOCK",
                name="clinicalruleaction",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "ACKNOWLEDGED",
                "OVERRIDDEN",
                "RESOLVED",
                "EXPIRED",
                name="clinicalalertstatus",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column(
            "deduplication_key",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rule_version > 0",
            name="ck_clinical_alerts_rule_version_positive",
        ),
        sa.CheckConstraint(
            "source_id IS NULL OR source_id > 0",
            name="ck_clinical_alerts_source_id_positive",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["clinical_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("clinical_alerts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_action"),
            ["action"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_clinic_id"),
            ["clinic_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_alerts_clinic_patient_status",
            ["clinic_id", "patient_id", "status", "generated_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_alerts_clinic_status_generated",
            ["clinic_id", "status", "generated_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_alerts_deduplication_key",
            ["deduplication_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_generated_at"),
            ["generated_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_patient_id"),
            ["patient_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_resolved_at"),
            ["resolved_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_rule_id"),
            ["rule_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_alerts_rule_version",
            ["rule_id", "rule_version", "generated_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_severity"),
            ["severity"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_alerts_source",
            ["source_type", "source_id", "generated_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_source_id"),
            ["source_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_source_type"),
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_alerts_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "alert_acknowledgements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column(
            "acknowledged_by_user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "acknowledgement_type",
            sa.Enum(
                "ACKNOWLEDGED",
                "OVERRIDDEN",
                name="alertacknowledgementtype",
            ),
            nullable=False,
        ),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["clinical_alerts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alert_id",
            "acknowledged_by_user_id",
            "acknowledgement_type",
            name="uq_alert_acknowledgement_actor_type",
        ),
    )

    with op.batch_alter_table(
        "alert_acknowledgements",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_alert_acknowledgements_acknowledged_at"),
            ["acknowledged_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_alert_acknowledgements_acknowledged_by_user_id"),
            ["acknowledged_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_alert_acknowledgements_acknowledgement_type"),
            ["acknowledgement_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_alert_acknowledgements_alert_created",
            ["alert_id", "acknowledged_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_alert_acknowledgements_alert_id"),
            ["alert_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_alert_acknowledgements_user_created",
            ["acknowledged_by_user_id", "acknowledged_at", "id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "alert_acknowledgements",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            "ix_alert_acknowledgements_user_created"
        )
        batch_op.drop_index(
            batch_op.f("ix_alert_acknowledgements_alert_id")
        )
        batch_op.drop_index(
            "ix_alert_acknowledgements_alert_created"
        )
        batch_op.drop_index(
            batch_op.f("ix_alert_acknowledgements_acknowledgement_type")
        )
        batch_op.drop_index(
            batch_op.f("ix_alert_acknowledgements_acknowledged_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_alert_acknowledgements_acknowledged_at")
        )

    op.drop_table("alert_acknowledgements")

    with op.batch_alter_table(
        "clinical_alerts",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_status")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_source_type")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_source_id")
        )
        batch_op.drop_index("ix_clinical_alerts_source")
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_severity")
        )
        batch_op.drop_index("ix_clinical_alerts_rule_version")
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_rule_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_resolved_at")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_patient_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_generated_at")
        )
        batch_op.drop_index(
            "ix_clinical_alerts_deduplication_key"
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_created_at")
        )
        batch_op.drop_index(
            "ix_clinical_alerts_clinic_status_generated"
        )
        batch_op.drop_index(
            "ix_clinical_alerts_clinic_patient_status"
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_clinic_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_alerts_action")
        )

    op.drop_table("clinical_alerts")

    with op.batch_alter_table(
        "clinical_rules",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_updated_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_severity")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_scope")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_rule_type")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_rule_code")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_is_hard_rule")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_enabled")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_effective_until")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_effective_from")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_department_code")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_created_by_user_id")
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_created_at")
        )
        batch_op.drop_index("ix_clinical_rules_code_scope")
        batch_op.drop_index(
            "ix_clinical_rules_clinic_type_enabled"
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_clinic_id")
        )
        batch_op.drop_index(
            "ix_clinical_rules_clinic_effective"
        )
        batch_op.drop_index(
            batch_op.f("ix_clinical_rules_action")
        )

    op.drop_table("clinical_rules")