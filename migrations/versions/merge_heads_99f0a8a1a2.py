"""
Merge migration to resolve multiple heads

Revision ID: merge_99f0a8a1a2
Revises: 5b5f4eaa713e, 1a2b3c4d5e6
Create Date: 2025-12-23 12:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_99f0a8a1a2'
down_revision = ('5b5f4eaa713e', '1a2b3c4d5e6')
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration; no DB changes required, it simply resolves multiple heads.
    pass


def downgrade():
    pass
