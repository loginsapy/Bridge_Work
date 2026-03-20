"""Add departments table and Supervisor role

Revision ID: 010_add_supervisor_and_departments
Revises: 009_add_webhook_deliveries
Create Date: 2026-03-18
"""

revision = '010_add_supervisor_and_departments'
down_revision = '009_add_webhook_deliveries'

from sqlalchemy import text


def upgrade(db):
    conn = db.engine.connect()

    # --- Create departments table ---
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS departments (
                id SERIAL PRIMARY KEY,
                name VARCHAR(128) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP
            )
        """))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"departments table may already exist: {e}")

    # --- Add department_id to users ---
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)"))
        conn.commit()
    except Exception:
        conn.rollback()
        print("users.department_id may already exist")

    # --- Add department_id to projects ---
    try:
        conn.execute(text("ALTER TABLE projects ADD COLUMN department_id INTEGER REFERENCES departments(id)"))
        conn.commit()
    except Exception:
        conn.rollback()
        print("projects.department_id may already exist")

    # --- Insert Supervisor role if it doesn't exist ---
    try:
        result = conn.execute(text("SELECT id FROM roles WHERE name = 'Supervisor'")).fetchone()
        if not result:
            conn.execute(text("INSERT INTO roles (name) VALUES ('Supervisor')"))
            conn.commit()
            print("Supervisor role created")
        else:
            print("Supervisor role already exists")
    except Exception as e:
        conn.rollback()
        print(f"Error inserting Supervisor role: {e}")

    conn.close()


def downgrade(db):
    conn = db.engine.connect()
    try:
        conn.execute(text("DELETE FROM roles WHERE name = 'Supervisor'"))
        conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS department_id"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS department_id"))
        conn.execute(text("DROP TABLE IF EXISTS departments"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Downgrade error: {e}")
    conn.close()
