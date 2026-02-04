"""Add license table

Revision ID: add_license_table
Revises: 
Create Date: 2025-01-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_license_table'
down_revision = '001_add_missing_task_columns'  # Refer to previous migration revision
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('license',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('license_key', sa.String(length=100), nullable=False),
        sa.Column('product_code', sa.String(length=50), nullable=True),
        sa.Column('hardware_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('last_validated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('license_type', sa.String(length=50), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=True),
        sa.Column('features', sa.Text(), nullable=True),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('customer_email', sa.String(length=200), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('license_key')
    )
    op.create_index(op.f('ix_license_status'), 'license', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_license_status'), table_name='license')
    op.drop_table('license')
