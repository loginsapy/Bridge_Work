"""Revert timezone-aware timestamps to naive TIMESTAMP

Revision ID: 003_revert_timestamps_to_naive
Revises: 002_rename_license_table
Create Date: 2026-02-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_revert_timestamps_to_naive'
down_revision = '003_timestamps_tz_aware'
branch_labels = None
depends_on = None


def _is_postgres():
    return op.get_bind().dialect.name == 'postgresql'


def upgrade():
    # Only perform ALTER TYPE operations on PostgreSQL; for SQLite we skip (no-op)
    if not _is_postgres():
        return

    # Convert timestamptz -> timestamp without time zone using UTC as reference
    conn = op.get_bind()

    # Tasks.completed_at
    op.alter_column(
        'tasks',
        'completed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        postgresql_using="completed_at AT TIME ZONE 'UTC'"
    )

    # AuditLog.created_at
    op.alter_column(
        'audit_logs',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'"
    )

    # SystemNotification.created_at
    op.alter_column(
        'system_notifications',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'"
    )

    # SystemSettings.updated_at
    op.alter_column(
        'system_settings',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        postgresql_using="updated_at AT TIME ZONE 'UTC'"
    )

    # Licenses timestamps (if they were created/converted previously)
    for col in ('activated_at', 'last_validated_at', 'expires_at', 'created_at', 'updated_at'):
        op.execute(
            f"ALTER TABLE licenses ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE USING ({col} AT TIME ZONE 'UTC')"
        )


def downgrade():
    # Reverse: convert naive timestamp -> timestamptz assuming stored values are UTC
    if not _is_postgres():
        return

    op.alter_column(
        'tasks',
        'completed_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="completed_at AT TIME ZONE 'UTC'"
    )

    op.alter_column(
        'audit_logs',
        'created_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'"
    )

    op.alter_column(
        'system_notifications',
        'created_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'"
    )

    op.alter_column(
        'system_settings',
        'updated_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="updated_at AT TIME ZONE 'UTC'"
    )

    for col in ('activated_at', 'last_validated_at', 'expires_at', 'created_at', 'updated_at'):
        op.execute(
            f"ALTER TABLE licenses ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE USING ({col} AT TIME ZONE 'UTC')"
        )
