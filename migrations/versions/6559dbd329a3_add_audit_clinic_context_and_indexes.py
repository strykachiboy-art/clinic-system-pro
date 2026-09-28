"""add audit clinic context and indexes

Revision ID: 6559dbd329a3
Revises: cc802fd6f67e
Create Date: 2026-09-28 18:22:36.308693

"""

from alembic import op
import sqlalchemy as sa


revision = "6559dbd329a3"
down_revision = "cc802fd6f67e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "clinic_id",
                sa.Integer(),
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE audit_logs
        SET clinic_id = users.clinic_id
        FROM users
        WHERE audit_logs.user_id = users.id
          AND users.clinic_id IS NOT NULL
        """
    )

    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_audit_logs_clinic_created_id",
            ["clinic_id", "created_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_audit_logs_clinic_entity_created_id",
            [
                "clinic_id",
                "entity_type",
                "entity_id",
                "created_at",
                "id",
            ],
            unique=False,
        )
        batch_op.create_index(
            "ix_audit_logs_clinic_user_created_id",
            [
                "clinic_id",
                "user_id",
                "created_at",
                "id",
            ],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_audit_logs_clinic_id_clinics",
            "clinics",
            ["clinic_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_audit_logs_clinic_id_clinics",
            type_="foreignkey",
        )
        batch_op.drop_index(
            "ix_audit_logs_clinic_user_created_id",
        )
        batch_op.drop_index(
            "ix_audit_logs_clinic_entity_created_id",
        )
        batch_op.drop_index(
            "ix_audit_logs_clinic_created_id",
        )
        batch_op.drop_column("clinic_id")