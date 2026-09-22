"""align PostgreSQL enums with application enums

Revision ID: 3f8c2e7a1b44
Revises: 2540f664a077
Create Date: 2026-09-22
"""

from alembic import op


revision = "3f8c2e7a1b44"
down_revision = "2540f664a077"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # LeaveType
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE public.leavetype "
        "ADD VALUE IF NOT EXISTS 'COMPASSIONATE'"
    )
    op.execute(
        "ALTER TYPE public.leavetype "
        "ADD VALUE IF NOT EXISTS 'EMERGENCY'"
    )
    op.execute(
        "ALTER TYPE public.leavetype "
        "ADD VALUE IF NOT EXISTS 'OTHER'"
    )
    op.execute(
        "ALTER TYPE public.leavetype "
        "ADD VALUE IF NOT EXISTS 'STUDY'"
    )

    # ------------------------------------------------------------------
    # MaintenanceStatus
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE public.maintenance_status "
        "ADD VALUE IF NOT EXISTS 'CANCELLED'"
    )

    # ------------------------------------------------------------------
    # TripStatus
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE public.tripstatus "
        "ADD VALUE IF NOT EXISTS 'PATIENT_ON_BOARD' "
        "AFTER 'AT_PICKUP'"
    )

    # ------------------------------------------------------------------
    # StockMovementType
    #
    # Legacy TRANSFER has no existing rows in this database.
    # Rename it to the new inbound transfer value, then add outbound.
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE public.stockmovementtype "
        "RENAME VALUE 'TRANSFER' TO 'TRANSFER_IN'"
    )

    op.execute(
        "ALTER TYPE public.stockmovementtype "
        "ADD VALUE IF NOT EXISTS 'TRANSFER_OUT' "
        "AFTER 'TRANSFER_IN'"
    )

    # ------------------------------------------------------------------
    # Legacy staffrole enum
    #
    # Verified unused by every table column.
    # ------------------------------------------------------------------
    op.execute(
        "DROP TYPE IF EXISTS public.staffrole"
    )


def downgrade():
    raise NotImplementedError(
        "Downgrade is intentionally unsupported because PostgreSQL "
        "enum value removal can be destructive and stock movement "
        "TRANSFER was split into TRANSFER_IN and TRANSFER_OUT."
    )