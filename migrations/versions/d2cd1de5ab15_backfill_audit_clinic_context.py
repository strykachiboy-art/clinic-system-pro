"""backfill audit clinic context

Revision ID: d2cd1de5ab15
Revises: 6559dbd329a3
Create Date: 2026-09-28 18:26:12.403662

"""

from alembic import op


revision = "d2cd1de5ab15"
down_revision = "6559dbd329a3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE audit_logs
        SET clinic_id = users.clinic_id
        FROM users
        WHERE audit_logs.user_id = users.id
          AND audit_logs.clinic_id IS NULL
          AND users.clinic_id IS NOT NULL
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE audit_logs
        SET clinic_id = NULL
        WHERE clinic_id IS NOT NULL
          AND user_id IS NOT NULL
        """
    )