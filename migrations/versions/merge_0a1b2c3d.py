"""merge heads 0a1b2c3d4e5f and add_assigned_client_to_tasks (short id)

Revision ID: merge_0a1b2c3d
Revises: 0a1b2c3d4e5f, add_assigned_client_to_tasks
Create Date: 2025-12-30 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_0a1b2c3d'
down_revision = ('0a1b2c3d4e5f', 'add_assigned_client_to_tasks')
branch_labels = None
dependencies = None


def upgrade():
    # Merge revision to unify multiple heads. No DB schema changes required.
    pass


def downgrade():
    # Not implemented - downgrading a merge revision is non-trivial.
    raise NotImplementedError("Cannot downgrade merge revision safely")
