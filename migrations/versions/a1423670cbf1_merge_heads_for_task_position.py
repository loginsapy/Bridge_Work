"""merge heads for task_position

Revision ID: a1423670cbf1
Revises: 41457cd927c5, add_task_position_column
Create Date: 2025-12-29 12:53:27.363545

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1423670cbf1'
down_revision = ('41457cd927c5', 'add_task_position_column')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
