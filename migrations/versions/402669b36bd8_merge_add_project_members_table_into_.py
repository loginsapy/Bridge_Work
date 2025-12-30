"""Merge add_project_members_table into main

Revision ID: 402669b36bd8
Revises: 11d44c669a90, add_project_members_table
Create Date: 2025-12-29 09:43:48.238805

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '402669b36bd8'
down_revision = ('11d44c669a90', 'add_project_members_table')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
