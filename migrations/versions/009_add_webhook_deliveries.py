"""
Add webhook_deliveries table

Revision ID: 009_add_webhook_deliveries
Revises: 008_add_project_risks
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa

revision = '009_add_webhook_deliveries'
down_revision = '008_add_project_risks'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'webhook_deliveries',
        sa.Column('id',            sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column('webhook_id',    sa.String(36),    nullable=False),
        sa.Column('webhook_name',  sa.String(200),   nullable=True),
        sa.Column('event',         sa.String(80),    nullable=False),
        sa.Column('url',           sa.String(500),   nullable=False),
        sa.Column('success',       sa.Boolean(),     nullable=False, server_default='0'),
        sa.Column('status_code',   sa.Integer(),     nullable=True),
        sa.Column('error_message', sa.Text(),        nullable=True),
        sa.Column('duration_ms',   sa.Integer(),     nullable=True),
        sa.Column('is_test',       sa.Boolean(),     server_default='0'),
        sa.Column('created_at',    sa.DateTime(),    nullable=True),
    )
    op.create_index('ix_webhook_deliveries_webhook_id', 'webhook_deliveries', ['webhook_id'])
    op.create_index('ix_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'])


def downgrade():
    op.drop_index('ix_webhook_deliveries_created_at', 'webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_webhook_id',  'webhook_deliveries')
    op.drop_table('webhook_deliveries')
