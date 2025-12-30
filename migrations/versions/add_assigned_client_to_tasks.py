"""add assigned client column to tasks

Revision ID: add_assigned_client_to_tasks
Revises: a1423670cbf1_merge_heads_for_task_position
Create Date: 2025-12-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_assigned_client_to_tasks'
down_revision = 'a1423670cbf1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('assigned_client_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tasks_assigned_client_id_users', 'tasks', 'users', ['assigned_client_id'], ['id'])
    op.create_index(op.f('ix_tasks_assigned_client_id'), 'tasks', ['assigned_client_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_tasks_assigned_client_id'), table_name='tasks')
    op.drop_constraint('fk_tasks_assigned_client_id_users', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'assigned_client_id')
