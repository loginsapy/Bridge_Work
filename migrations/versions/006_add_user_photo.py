"""
Add photo columns to users

Revision ID: 006_add_user_photo
Revises: 005_add_comment_parent
Create Date: 2026-02-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_user_photo'
down_revision = '005_add_comment_parent'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'users' not in inspector.get_table_names():
        return

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('photo', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('photo_mime', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('photo_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'users' not in inspector.get_table_names():
        return

    with op.batch_alter_table('users') as batch_op:
        try:
            batch_op.drop_column('photo_updated_at')
        except Exception:
            pass
        try:
            batch_op.drop_column('photo_mime')
        except Exception:
            pass
        try:
            batch_op.drop_column('photo')
        except Exception:
            pass