"""Add task_clients many-to-many table

Revision ID: 011_add_task_clients
Revises: 010_add_supervisor_and_departments
Create Date: 2026-03-18
"""

revision = '011_add_task_clients'
down_revision = '010_add_supervisor_and_departments'

import sqlalchemy as sa
from sqlalchemy import text


def upgrade(db):
    conn = db.engine.connect()
    dialect = db.engine.dialect.name

    try:
        if dialect == 'sqlite':
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_clients (
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, user_id)
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_clients (
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, user_id)
                )
            """))
        conn.commit()
        print("task_clients table created")
    except Exception as e:
        conn.rollback()
        print(f"task_clients table may already exist: {e}")

    conn.close()


def downgrade(db):
    conn = db.engine.connect()
    try:
        conn.execute(text("DROP TABLE IF EXISTS task_clients"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Downgrade error: {e}")
    conn.close()
