"""merge heads for task_predecessors

Revision ID: 41457cd927c5
Revises: 402669b36bd8, add_task_predecessors_table
Create Date: 2025-12-29 12:05:33.198355

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '41457cd927c5'
down_revision = ('402669b36bd8', 'add_task_predecessors_table')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
