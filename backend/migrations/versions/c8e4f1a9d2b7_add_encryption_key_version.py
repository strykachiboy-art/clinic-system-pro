"""add integration encryption key version metadata

Revision ID: c8e4f1a9d2b7
Revises: d7f4a6b91c22
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e4f1a9d2b7"
down_revision = "d7f4a6b91c22"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "integration_configs",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "encryption_key_version",
                sa.Integer(),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE integration_configs
            SET encryption_key_version = 1
            WHERE encryption_key_version IS NULL
            """
        )
    )

    with op.batch_alter_table(
        "integration_configs",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "encryption_key_version",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_integration_config_encryption_key_version_positive",
            "encryption_key_version >= 1",
        )


def downgrade():
    with op.batch_alter_table(
        "integration_configs",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_integration_config_encryption_key_version_positive",
            type_="check",
        )
        batch_op.drop_column(
            "encryption_key_version"
        )
