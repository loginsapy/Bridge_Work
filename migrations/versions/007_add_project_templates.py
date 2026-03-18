"""
Add project_templates and project_template_tasks tables

Revision ID: 007_add_project_templates
Revises: 006_add_user_photo
Create Date: 2026-03-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_add_project_templates'
down_revision = '006_add_user_photo'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    if 'project_templates' not in existing:
        op.create_table(
            'project_templates',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('project_type', sa.String(32), nullable=True, server_default='APP_DEVELOPMENT'),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )

    if 'project_template_tasks' not in existing:
        op.create_table(
            'project_template_tasks',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('template_id', sa.Integer(), sa.ForeignKey('project_templates.id'), nullable=False),
            sa.Column('source_task_id', sa.Integer(), nullable=True),
            sa.Column('parent_source_id', sa.Integer(), nullable=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('priority', sa.String(16), nullable=True, server_default='MEDIUM'),
            sa.Column('estimated_hours', sa.Numeric(8, 2), nullable=True),
            sa.Column('relative_start_days', sa.Integer(), nullable=True),
            sa.Column('relative_due_days', sa.Integer(), nullable=True),
            sa.Column('position', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('is_external_visible', sa.Boolean(), nullable=True, server_default='0'),
            sa.Column('requires_approval', sa.Boolean(), nullable=True, server_default='1'),
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    if 'project_template_tasks' in existing:
        op.drop_table('project_template_tasks')
    if 'project_templates' in existing:
        op.drop_table('project_templates')
