import sqlalchemy as sa, os
engine = sa.create_engine(os.environ.get('DATABASE_URL'))
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
