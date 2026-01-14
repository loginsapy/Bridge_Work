"""Drop backup tables created during the migration dry-run process.
"""
import os
import sqlalchemy as sa

# Safety: prevent accidental drops against non-local DBs unless explicitly confirmed
from app.utils.safety import is_safe_db_uri, require_confirmation

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
if not is_safe_db_uri(DATABASE_URL):
    if not require_confirmation('CONFIRM_DROP_BACKUPS'):
        print("Refusing to drop backup tables: DATABASE_URL appears remote. Set CONFIRM_DROP_BACKUPS=YES to proceed.")
        raise SystemExit(1)

engine = sa.create_engine(DATABASE_URL)

with engine.begin() as conn:
    print('Dropping tables if exist: task_predecessors_backup, tasks_backup')
    conn.execute(sa.text('DROP TABLE IF EXISTS task_predecessors_backup'))
    conn.execute(sa.text('DROP TABLE IF EXISTS tasks_backup'))

print('Done')
