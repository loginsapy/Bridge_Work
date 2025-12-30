"""
Add role_id to users and enforce projects.client_id FK; seed roles

Revision ID: 1a2b3c4d5e6
Revises: 6776b38e5319
Create Date: 2025-12-23 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6'
down_revision = '6776b38e5319'
branch_labels = None
depends_on = None


def upgrade():
    # Add role_id to users
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_role_id_roles', 'users', 'roles', ['role_id'], ['id'])

    # Enforce projects.client_id FK to users
    op.create_foreign_key('fk_projects_client_id_users', 'projects', 'users', ['client_id'], ['id'])

    # Seed roles
    roles_table = table('roles', column('name', sa.String))
    op.bulk_insert(roles_table, [
        {'name': 'Participante'},
        {'name': 'PMP'},
        {'name': 'Cliente'},
    ])

    # Assign role ids for known users if they exist
    op.execute("UPDATE users SET role_id = (SELECT id FROM roles WHERE name='PMP') WHERE email='admin@bridgework.com';")
    op.execute("UPDATE users SET role_id = (SELECT id FROM roles WHERE name='Cliente') WHERE email='client@example.com';")

    # Assign project 1 to client@example.com for testing (if both exist)
    op.execute("UPDATE projects SET client_id = (SELECT id FROM users WHERE email='client@example.com') WHERE id = 1 AND (SELECT id FROM users WHERE email='client@example.com') IS NOT NULL;")


def downgrade():
    # Remove seeded role references
    op.execute("UPDATE users SET role_id = NULL WHERE email IN ('admin@bridgework.com', 'client@example.com');")

    # Drop foreign keys
    op.drop_constraint('fk_projects_client_id_users', 'projects', type_='foreignkey')
    op.drop_constraint('fk_users_role_id_roles', 'users', type_='foreignkey')

    # Drop role_id column
    op.drop_column('users', 'role_id')

    # Remove seeded roles (best-effort)
    op.execute("DELETE FROM roles WHERE name IN ('Participante', 'PMP', 'Cliente');")
    # Also clean up old typo if it exists
    op.execute("DELETE FROM roles WHERE name = 'Particpante';")
