"""Check whether core app tables exist in the database."""
import os
import sqlalchemy as sa

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
engine = sa.create_engine(DATABASE_URL)

tables_to_check = ['users', 'projects', 'tasks', 'task_predecessors', 'alembic_version']

with engine.connect() as conn:
    for t in tables_to_check:
        r = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)") , {'t': t})
        print(f"{t}:", r.scalar())
