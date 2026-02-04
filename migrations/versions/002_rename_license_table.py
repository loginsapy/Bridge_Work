"""Rename license table to licenses (fix incorrect table name)

Revision ID: 002_rename_license_table
Revises: add_license_table
Create Date: 2026-02-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_rename_license_table'
down_revision = 'add_license_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'licenses' not in tables and 'license' in tables:
        # Rename table to match model's __tablename__
        op.rename_table('license', 'licenses')


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'license' not in tables and 'licenses' in tables:
        op.rename_table('licenses', 'license')
