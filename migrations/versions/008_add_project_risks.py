"""
Add project_risks table

Revision ID: 008_add_project_risks
Revises: 007_add_project_templates
Create Date: 2026-03-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '008_add_project_risks'
down_revision = '007_add_project_templates'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    if 'project_risks' not in existing:
        op.create_table(
            'project_risks',
            sa.Column('id',          sa.Integer(),     primary_key=True, autoincrement=True),
            sa.Column('project_id',  sa.Integer(),     sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('type',        sa.String(16),    nullable=False,  server_default='RISK'),
            sa.Column('title',       sa.String(255),   nullable=False),
            sa.Column('description', sa.Text(),        nullable=True),
            sa.Column('severity',    sa.String(16),    nullable=False,  server_default='MEDIUM'),
            sa.Column('probability', sa.String(16),    nullable=True,   server_default='MEDIUM'),
            sa.Column('status',      sa.String(16),    nullable=False,  server_default='OPEN'),
            sa.Column('mitigation_plan', sa.Text(),    nullable=True),
            sa.Column('owner_id',    sa.Integer(),     sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_by_id', sa.Integer(),   sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at',  sa.DateTime(),    nullable=True),
            sa.Column('updated_at',  sa.DateTime(),    nullable=True),
        )
        op.create_index('ix_project_risks_project_id', 'project_risks', ['project_id'])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()
    if 'project_risks' in existing:
        op.drop_index('ix_project_risks_project_id', table_name='project_risks')
        op.drop_table('project_risks')
