"""Merge heads

Revision ID: e522cd0e9f61
Revises: 5c6766ddd2a2, add_task_assignees_table
Create Date: 2026-01-19 11:25:14.883993

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e522cd0e9f61'
down_revision = ('5c6766ddd2a2', 'add_task_assignees_table')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
