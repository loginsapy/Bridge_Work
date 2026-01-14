import sqlalchemy as sa, os
from app.utils.safety import is_safe_db_uri, require_confirmation
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise SystemExit('DATABASE_URL not set')
if not is_safe_db_uri(DATABASE_URL) and not require_confirmation('ALLOW_REMOTE_INSPECT'):
    print('Refusing to inspect backups on remote DB. Set ALLOW_REMOTE_INSPECT=YES to proceed.')
    raise SystemExit(1)

engine = sa.create_engine(DATABASE_URL)
with engine.connect() as conn:
    # Check backups
    r1 = conn.execute(sa.text("SELECT count(*) FROM information_schema.tables WHERE table_name='tasks_backup' OR table_name='task_predecessors_backup'"))
    print('backup tables count:', r1.scalar())
    # Show first few rows of report
    try:
        with open('migration_parent_conversion_report.csv') as f:
            print('\nREPORT:\n', f.read())
    except Exception as e:
        print('Could not read report:', e)
