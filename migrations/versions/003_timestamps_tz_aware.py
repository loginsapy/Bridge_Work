"""Make timestamps timezone-aware (placeholder)

Revision ID: 003_timestamps_tz_aware
Revises: 002_rename_license_table
Create Date: 2026-01-20

Note: This placeholder exists because the original migration file was removed during a revert. The real DB already reflects this revision; this file is a no-op to satisfy Alembic's revision history.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_timestamps_tz_aware'
down_revision = '002_rename_license_table'
branch_labels = None
depends_on = None


def upgrade():
    # No-op placeholder
    pass


def downgrade():
    # No-op placeholder
    pass
