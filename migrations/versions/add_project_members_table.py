"""
Add project_members association table

Revision ID: add_project_members_table
Revises: 1a2b3c4d5e6
Create Date: 2025-12-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_project_members_table'
down_revision = '1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'project_members',
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True)
    )


def downgrade():
    op.drop_table('project_members')
