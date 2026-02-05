"""Add parent_id to task_comments for threaded replies

Revision ID: 005_add_comment_parent
Revises: 004_add_task_comments
Create Date: 2026-02-05 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_comment_parent'
down_revision = '004_add_task_comments'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'task_comments' not in inspector.get_table_names():
        return

    # add column parent_id
    with op.batch_alter_table('task_comments') as batch_op:
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_task_comments_parent', 'task_comments', ['parent_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index('ix_task_comments_parent_id', ['parent_id'])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'task_comments' not in inspector.get_table_names():
        return

    with op.batch_alter_table('task_comments') as batch_op:
        try:
            batch_op.drop_index('ix_task_comments_parent_id')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('fk_task_comments_parent', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_column('parent_id')
        except Exception:
            pass
