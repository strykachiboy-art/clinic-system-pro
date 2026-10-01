"""add staff department memberships

Revision ID: 4d205e66d288
Revises: 691c9a0e0942
Create Date: 2026-10-01 13:09:48.135732

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from typing import cast


revision = "4d205e66d288"
down_revision = "691c9a0e0942"
branch_labels = None
depends_on = None


staff_department_status = postgresql.ENUM(
    "ACTIVE",
    "INACTIVE",
    "ENDED",
    name="staffdepartmentstatus",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()

    staff_department_status.create(
        bind,
        checkfirst=True,
    )

    op.add_column(
        "staff",
        sa.Column(
            "department_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_staff_department_id",
        "staff",
        ["department_id"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_staff_id_clinic",
        "staff",
        ["id", "clinic_id"],
    )

    op.create_unique_constraint(
        "uq_departments_id_clinic",
        "departments",
        ["id", "clinic_id"],
    )

    op.create_foreign_key(
        "fk_staff_department_department",
        "staff",
        "departments",
        ["department_id"],
        ["id"],
    )

    op.create_table(
        "staff_departments",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "clinic_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "status",
            cast(
                sa.types.TypeEngine[str],
                staff_department_status,
            ),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status != 'ENDED' OR ended_at IS NOT NULL",
            name="ck_staff_departments_ended_requires_end",
        ),
        sa.CheckConstraint(
            "status = 'ACTIVE' OR is_primary = FALSE",
            name="ck_staff_departments_primary_active_only",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR assigned_at <= ended_at",
            name="ck_staff_departments_valid_period",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_staff_departments_clinic",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_staff_departments_staff_clinic",
        ),
        sa.ForeignKeyConstraint(
            ["department_id", "clinic_id"],
            ["departments.id", "departments.clinic_id"],
            name="fk_staff_departments_department_clinic",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_staff_departments_clinic_id",
        "staff_departments",
        ["clinic_id"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_staff_id",
        "staff_departments",
        ["staff_id"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_department_id",
        "staff_departments",
        ["department_id"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_status",
        "staff_departments",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_ended_at",
        "staff_departments",
        ["ended_at"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_clinic_staff_status",
        "staff_departments",
        ["clinic_id", "staff_id", "status"],
        unique=False,
    )

    op.create_index(
        "ix_staff_departments_clinic_department_status",
        "staff_departments",
        ["clinic_id", "department_id", "status"],
        unique=False,
    )

    op.create_index(
        "uq_staff_departments_active_membership",
        "staff_departments",
        ["clinic_id", "staff_id", "department_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ACTIVE'"
        ),
    )

    op.create_index(
        "uq_staff_departments_active_primary",
        "staff_departments",
        ["clinic_id", "staff_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND is_primary = TRUE"
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO staff_departments (
                clinic_id,
                staff_id,
                department_id,
                is_primary,
                status,
                assigned_at,
                ended_at,
                created_at,
                updated_at
            )
            SELECT
                s.clinic_id,
                s.id,
                s.department_id,
                TRUE,
                'ACTIVE',
                COALESCE(
                    s.created_at,
                    CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                ),
                NULL,
                COALESCE(
                    s.created_at,
                    CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                ),
                COALESCE(
                    s.updated_at,
                    CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
                )
            FROM staff AS s
            WHERE s.department_id IS NOT NULL
            """
        )
    )


def downgrade():
    op.drop_index(
        "uq_staff_departments_active_primary",
        table_name="staff_departments",
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND is_primary = TRUE"
        ),
    )

    op.drop_index(
        "uq_staff_departments_active_membership",
        table_name="staff_departments",
        postgresql_where=sa.text(
            "status = 'ACTIVE'"
        ),
    )

    op.drop_index(
        "ix_staff_departments_clinic_department_status",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_clinic_staff_status",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_ended_at",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_status",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_department_id",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_staff_id",
        table_name="staff_departments",
    )

    op.drop_index(
        "ix_staff_departments_clinic_id",
        table_name="staff_departments",
    )

    op.drop_table(
        "staff_departments"
    )

    op.drop_constraint(
        "fk_staff_department_department",
        "staff",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_staff_id_clinic",
        "staff",
        type_="unique",
    )

    op.drop_index(
        "ix_staff_department_id",
        table_name="staff",
    )

    op.drop_column(
        "staff",
        "department_id",
    )

    op.drop_constraint(
        "uq_departments_id_clinic",
        "departments",
        type_="unique",
    )

    staff_department_status.drop(
        op.get_bind(),
        checkfirst=True,
    )
