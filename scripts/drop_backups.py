"""Drop backup tables created during the migration dry-run process.
"""
import os
import sqlalchemy as sa

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
engine = sa.create_engine(DATABASE_URL)

with engine.begin() as conn:
    print('Dropping tables if exist: task_predecessors_backup, tasks_backup')
    conn.execute(sa.text('DROP TABLE IF EXISTS task_predecessors_backup'))
    conn.execute(sa.text('DROP TABLE IF EXISTS tasks_backup'))

print('Done')
