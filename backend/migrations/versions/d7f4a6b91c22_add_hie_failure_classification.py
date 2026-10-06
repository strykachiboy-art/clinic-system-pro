"""persist HIE submission failure classification

Revision ID: d7f4a6b91c22
Revises: a91c2f3e7b44
Create Date: 2026-10-06 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d7f4a6b91c22"
down_revision = "a91c2f3e7b44"
branch_labels = None
depends_on = None


hie_failure_class = postgresql.ENUM(
    "RETRYABLE",
    "RECONCILIATION_REQUIRED",
    "USER_ACTION_REQUIRED",
    "FAIL_CLOSED",
    name="hiefailureclass",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()

    hie_failure_class.create(
        bind,
        checkfirst=True,
    )

    op.add_column(
        "hie_submissions",
        sa.Column(
            "failure_class",
            hie_failure_class,
            nullable=True,
        ),
    )

    op.create_index(
        "ix_hie_submissions_failure_class",
        "hie_submissions",
        ["failure_class"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_hie_submissions_failure_class",
        table_name="hie_submissions",
    )

    op.drop_column(
        "hie_submissions",
        "failure_class",
    )

    hie_failure_class.drop(
        op.get_bind(),
        checkfirst=True,
    )