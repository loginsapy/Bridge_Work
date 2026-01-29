"""Add missing columns to tasks table

Revision ID: 001_add_missing_task_columns
Revises: 
Create Date: 2025-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_missing_task_columns'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Obtener el inspector para verificar columnas existentes antes de intentar agregarlas
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('tasks')]
    
    # completed_at
    if 'completed_at' not in existing_columns:
        op.add_column('tasks', sa.Column('completed_at', sa.DateTime(), nullable=True))
    
    # is_external_visible
    if 'is_external_visible' not in existing_columns:
        op.add_column('tasks', sa.Column('is_external_visible', sa.Boolean(), default=False, nullable=False))
    
    # is_internal_only
    if 'is_internal_only' not in existing_columns:
        op.add_column('tasks', sa.Column('is_internal_only', sa.Boolean(), default=False, nullable=False))
    
    # estimated_hours
    if 'estimated_hours' not in existing_columns:
        op.add_column('tasks', sa.Column('estimated_hours', sa.Numeric(), nullable=True))
    
    # position
    if 'position' not in existing_columns:
        op.add_column('tasks', sa.Column('position', sa.Integer(), nullable=True))
    
    # requires_approval
    if 'requires_approval' not in existing_columns:
        op.add_column('tasks', sa.Column('requires_approval', sa.Boolean(), default=True, nullable=False))
    
    # approval_status
    if 'approval_status' not in existing_columns:
        op.add_column('tasks', sa.Column('approval_status', sa.String(32), nullable=True))
    
    # approved_by_id (Foreign Key)
    if 'approved_by_id' not in existing_columns:
        op.add_column('tasks', sa.Column('approved_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_tasks_approved_by_id', 'tasks', 'users', ['approved_by_id'], ['id'])
    
    # approved_at
    if 'approved_at' not in existing_columns:
        op.add_column('tasks', sa.Column('approved_at', sa.DateTime(), nullable=True))
    
    # approval_notes
    if 'approval_notes' not in existing_columns:
        op.add_column('tasks', sa.Column('approval_notes', sa.Text(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('tasks')]

    # Remover columnas agregadas
    columns_to_drop = [
        'approval_notes', 'approved_at', 'approved_by_id', 
        'approval_status', 'requires_approval', 'position', 
        'estimated_hours', 'is_internal_only', 'is_external_visible', 
        'completed_at'
    ]
    
    for col in columns_to_drop:
        if col in existing_columns:
            op.drop_column('tasks', col)
