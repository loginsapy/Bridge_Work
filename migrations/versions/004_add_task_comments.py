"""Add task_comments table

Revision ID: 004_add_task_comments
Revises: 003_timestamps_tz_aware
Create Date: 2026-02-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_add_task_comments'
down_revision = '003_timestamps_tz_aware'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'task_comments' in inspector.get_table_names():
        return

    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'task_comments' in inspector.get_table_names():
        op.drop_table('task_comments')
