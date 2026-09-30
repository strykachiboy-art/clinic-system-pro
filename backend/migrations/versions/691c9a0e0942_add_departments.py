"""add departments

Revision ID: 691c9a0e0942
Revises: d2cd1de5ab15
Create Date: 2026-09-30 17:16:37.971719

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '691c9a0e0942'
down_revision = 'd2cd1de5ab15'
branch_labels = None
depends_on = None


department_status = postgresql.ENUM(
    'ACTIVE',
    'INACTIVE',
    'SUSPENDED',
    name='departmentstatus',
    create_type=False,
)


def upgrade():
    department_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', department_status, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['clinic_id'],
            ['clinics.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'clinic_id',
            'code',
            name='uq_departments_clinic_code',
        ),
        sa.UniqueConstraint(
            'clinic_id',
            'name',
            name='uq_departments_clinic_name',
        ),
    )

    op.create_index(
        'ix_departments_clinic_id',
        'departments',
        ['clinic_id'],
        unique=False,
    )
    op.create_index(
        'ix_departments_clinic_status_name',
        'departments',
        ['clinic_id', 'status', 'name', 'id'],
        unique=False,
    )
    op.create_index(
        'ix_departments_status',
        'departments',
        ['status'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_departments_status',
        table_name='departments',
    )
    op.drop_index(
        'ix_departments_clinic_status_name',
        table_name='departments',
    )
    op.drop_index(
        'ix_departments_clinic_id',
        table_name='departments',
    )

    op.drop_table('departments')

    department_status.drop(op.get_bind(), checkfirst=True)
