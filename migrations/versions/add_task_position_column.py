"""add task position column

Revision ID: add_task_position_column
Revises: 41457cd927c5
Create Date: 2025-12-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_task_position_column'
down_revision = '41457cd927c5'
branch_labels = None
dependencies = None


def upgrade():
    # Add the 'position' column to 'tasks' if it doesn't exist.
    try:
        op.add_column('tasks', sa.Column('position', sa.Integer(), nullable=True))
    except Exception:
        # Column likely already exists; ignore to make this migration idempotent
        pass

    # Create an index on position to match previous expectations if not present
    try:
        op.create_index('ix_tasks_position', 'tasks', ['position'])
    except Exception:
        pass


def downgrade():
    # Attempt to drop the index and column; ignore errors if they don't exist
    try:
        op.drop_index('ix_tasks_position', table_name='tasks')
    except Exception:
        pass

    try:
        op.drop_column('tasks', 'position')
    except Exception:
        pass
