"""
Add task_predecessors association table

Revision ID: add_task_predecessors_table
Revises: e4f706ecd984
Create Date: 2025-12-29 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_task_predecessors_table'
down_revision = 'e4f706ecd984'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'task_predecessors',
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), primary_key=True),
        sa.Column('predecessor_id', sa.Integer(), sa.ForeignKey('tasks.id'), primary_key=True),
    )


def downgrade():
    op.drop_table('task_predecessors')
