"""Normalize legacy DONE statuses to COMPLETED

Revision ID: c3f1d2a9b8e7
Revises: e522cd0e9f61
Create Date: 2026-01-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3f1d2a9b8e7'
down_revision = 'e522cd0e9f61'
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent update: convert any legacy 'DONE' to canonical 'COMPLETED'
    op.execute("""
        UPDATE tasks
        SET status = 'COMPLETED'
        WHERE status = 'DONE'
    """)


def downgrade():
    # Downgrade is intentionally broad — it will set COMPLETED back to DONE.
    # Use with caution and prefer restoring from backups if needed.
    op.execute("""
        UPDATE tasks
        SET status = 'DONE'
        WHERE status = 'COMPLETED'
    """)
