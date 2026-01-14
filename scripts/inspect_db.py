import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    insp = db.inspect(db.engine)
    tables = insp.get_table_names()
    print('Tables:', tables)
    def count(table):
        try:
            r = db.session.execute(text(f'SELECT count(*) FROM {table}')).scalar()
            return r
        except Exception as e:
            return f'ERR: {e}'

    for t in ['users','projects','tasks','system_notifications','audit_logs','system_settings']:
        if t in tables:
            print(f"{t}:", count(t))
        else:
            print(f"{t}: MISSING")

    # show last 10 audit logs
    if 'audit_logs' in tables:
        rows = db.session.execute(text('SELECT id, entity_type, entity_id, action, user_id, created_at FROM audit_logs ORDER BY created_at DESC NULLS LAST LIMIT 20')).fetchall()
        print('\nLast audit logs:')
        for r in rows:
            print(r)

    # show sample users
    if 'users' in tables:
        rows = db.session.execute(text('SELECT id, email, first_name, last_name, created_at FROM users ORDER BY created_at DESC NULLS LAST LIMIT 20')).fetchall()
        print('\nSample users:')
        for r in rows:
            print(r)
