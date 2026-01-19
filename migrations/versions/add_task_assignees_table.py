"""
Add task_assignees association table

Revision ID: add_task_assignees_table
Revises: add_task_predecessors_table
Create Date: 2026-01-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_task_assignees_table'
down_revision = 'add_task_predecessors_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'task_assignees',
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
    )

    # Backfill existing assigned_to_id into task_assignees
    op.execute("""
        INSERT INTO task_assignees (task_id, user_id)
        SELECT id as task_id, assigned_to_id as user_id FROM tasks WHERE assigned_to_id IS NOT NULL
    """)


def downgrade():
    op.drop_table('task_assignees')
