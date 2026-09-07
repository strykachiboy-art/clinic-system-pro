"""Ai and others updated

Revision ID: fc0a300e625a
Revises: 5284601c0e15
Create Date: 2026-09-06 20:04:04.188884

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "fc0a300e625a"
down_revision = "5284601c0e15"
branch_labels = None
depends_on = None


def upgrade():
    # ================================================================
    # AI ENUM TYPES
    # ================================================================

    ai_risk_level = postgresql.ENUM(
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
        name="airisklevel",
    )

    ai_approval_status = postgresql.ENUM(
        "PENDING",
        "APPROVED",
        "REJECTED",
        name="aiapprovalstatus",
    )

    ai_risk_level.create(
        op.get_bind(),
        checkfirst=True,
    )

    ai_approval_status.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ================================================================
    # AI LOGS
    # ================================================================

    with op.batch_alter_table(
        "ai_logs",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "risk_level",
                postgresql.ENUM(
                    "LOW",
                    "MEDIUM",
                    "HIGH",
                    "CRITICAL",
                    name="airisklevel",
                    create_type=False,
                ),
                nullable=False,
                server_default="LOW",
            )
        )

        batch_op.add_column(
            sa.Column(
                "model",
                sa.String(length=100),
                nullable=False,
                server_default="unknown",
            )
        )

        batch_op.add_column(
            sa.Column(
                "model_version",
                sa.String(length=100),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "input_context_version",
                sa.String(length=100),
                nullable=False,
                server_default="v1",
            )
        )

        batch_op.add_column(
            sa.Column(
                "generated_by_system",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

        batch_op.add_column(
            sa.Column(
                "approval_status",
                postgresql.ENUM(
                    "PENDING",
                    "APPROVED",
                    "REJECTED",
                    name="aiapprovalstatus",
                    create_type=False,
                ),
                nullable=False,
                server_default="PENDING",
            )
        )

        batch_op.add_column(
            sa.Column(
                "input_tokens",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "output_tokens",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "total_tokens",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "estimated_cost",
                sa.Numeric(
                    precision=12,
                    scale=6,
                ),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "cost_currency",
                sa.String(length=10),
                nullable=True,
            )
        )

        batch_op.alter_column(
            "created_at",
            existing_type=postgresql.TIMESTAMP(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )

        batch_op.alter_column(
            "updated_at",
            existing_type=postgresql.TIMESTAMP(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_logs_approval_status"),
            ["approval_status"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_logs_generated_by_system"),
            ["generated_by_system"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_logs_risk_level"),
            ["risk_level"],
            unique=False,
        )

        # ------------------------------------------------------------
        # Remove migration-only server defaults.
        # The application model remains responsible for defaults.
        # ------------------------------------------------------------

        batch_op.alter_column(
            "risk_level",
            server_default=None,
        )

        batch_op.alter_column(
            "model",
            server_default=None,
        )

        batch_op.alter_column(
            "input_context_version",
            server_default=None,
        )

        batch_op.alter_column(
            "generated_by_system",
            server_default=None,
        )

        batch_op.alter_column(
            "approval_status",
            server_default=None,
        )

    # ================================================================
    # AI REVIEWS
    # ================================================================

    op.create_table(
        "ai_reviews",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ai_log_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "APPROVED",
                "REJECTED",
                name="aiapprovalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "review_notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "reviewed_at",
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
            ["ai_log_id"],
            ["ai_logs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table(
        "ai_reviews",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ai_reviews_ai_log_id"),
            ["ai_log_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_reviews_reviewed_at"),
            ["reviewed_at"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_reviews_reviewer_id"),
            ["reviewer_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_ai_reviews_status"),
            ["status"],
            unique=False,
        )

    # ================================================================
    # DRUG INTERACTIONS
    # ================================================================

    with op.batch_alter_table(
        "drug_interactions",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_drug_interactions_drug_a_id"),
            ["drug_a_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_drug_interactions_drug_b_id"),
            ["drug_b_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_drug_interactions_severity"),
            ["severity"],
            unique=False,
        )

    # ================================================================
    # GENERATED REPORTS
    # ================================================================

    with op.batch_alter_table(
        "generated_reports",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_generated_reports_created_at"),
            ["created_at"],
            unique=False,
        )

    # ================================================================
    # PRESCRIPTION ITEMS
    # ================================================================

    with op.batch_alter_table(
        "prescription_items",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_prescription_items_drug_id"),
            ["drug_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescription_items_prescription_id"),
            ["prescription_id"],
            unique=False,
        )

    # ================================================================
    # PRESCRIPTIONS
    # ================================================================

    with op.batch_alter_table(
        "prescriptions",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "issued_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=False,
        )

        batch_op.alter_column(
            "created_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=False,
        )

        batch_op.alter_column(
            "updated_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescriptions_clinic_id"),
            ["clinic_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescriptions_consultation_id"),
            ["consultation_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescriptions_patient_id"),
            ["patient_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescriptions_prescribed_by_id"),
            ["prescribed_by_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f("ix_prescriptions_status"),
            ["status"],
            unique=False,
        )


def downgrade():
    # ================================================================
    # PRESCRIPTIONS
    # ================================================================

    with op.batch_alter_table(
        "prescriptions",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_prescriptions_status")
        )

        batch_op.drop_index(
            batch_op.f("ix_prescriptions_prescribed_by_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_prescriptions_patient_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_prescriptions_consultation_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_prescriptions_clinic_id")
        )

        batch_op.alter_column(
            "updated_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=True,
        )

        batch_op.alter_column(
            "created_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=True,
        )

        batch_op.alter_column(
            "issued_at",
            existing_type=postgresql.TIMESTAMP(),
            nullable=True,
        )

    # ================================================================
    # PRESCRIPTION ITEMS
    # ================================================================

    with op.batch_alter_table(
        "prescription_items",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_prescription_items_prescription_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_prescription_items_drug_id")
        )

    # ================================================================
    # GENERATED REPORTS
    # ================================================================

    with op.batch_alter_table(
        "generated_reports",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_generated_reports_created_at")
        )

    # ================================================================
    # DRUG INTERACTIONS
    # ================================================================

    with op.batch_alter_table(
        "drug_interactions",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_drug_interactions_severity")
        )

        batch_op.drop_index(
            batch_op.f("ix_drug_interactions_drug_b_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_drug_interactions_drug_a_id")
        )

    # ================================================================
    # AI REVIEWS
    # ================================================================

    with op.batch_alter_table(
        "ai_reviews",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_ai_reviews_status")
        )

        batch_op.drop_index(
            batch_op.f("ix_ai_reviews_reviewer_id")
        )

        batch_op.drop_index(
            batch_op.f("ix_ai_reviews_reviewed_at")
        )

        batch_op.drop_index(
            batch_op.f("ix_ai_reviews_ai_log_id")
        )

    op.drop_table("ai_reviews")

    # ================================================================
    # AI LOGS
    # ================================================================

    with op.batch_alter_table(
        "ai_logs",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_ai_logs_risk_level")
        )

        batch_op.drop_index(
            batch_op.f("ix_ai_logs_generated_by_system")
        )

        batch_op.drop_index(
            batch_op.f("ix_ai_logs_approval_status")
        )

        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=postgresql.TIMESTAMP(),
            existing_nullable=False,
        )

        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=postgresql.TIMESTAMP(),
            existing_nullable=False,
        )

        batch_op.drop_column("cost_currency")
        batch_op.drop_column("estimated_cost")
        batch_op.drop_column("total_tokens")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("approval_status")
        batch_op.drop_column("generated_by_system")
        batch_op.drop_column("input_context_version")
        batch_op.drop_column("model_version")
        batch_op.drop_column("model")
        batch_op.drop_column("risk_level")

    # ================================================================
    # AI ENUM TYPES
    # ================================================================

    ai_approval_status = postgresql.ENUM(
        "PENDING",
        "APPROVED",
        "REJECTED",
        name="aiapprovalstatus",
    )

    ai_risk_level = postgresql.ENUM(
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
        name="airisklevel",
    )

    ai_approval_status.drop(
        op.get_bind(),
        checkfirst=True,
    )

    ai_risk_level.drop(
        op.get_bind(),
        checkfirst=True,
    )