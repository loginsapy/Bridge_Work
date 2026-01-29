"""Add completed_at column to tasks

Revision ID: 001_add_completed_at
Revises: 
Create Date: 2025-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_completed_at'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Agregar columna completed_at a tasks
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remover columna si se revierte
    op.drop_column('tasks', 'completed_at')
