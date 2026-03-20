"""Inspect the PostgreSQL schema of key tables. Requires DATABASE_URL to be set."""
from app import create_app, db
from sqlalchemy import text

app = create_app('config.DevConfig')
with app.app_context():
    with db.engine.connect() as conn:
        res = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
        """)).fetchall()
        print('users table columns:')
        for row in res:
            print(' ', row)

    from app.models import User
    print('\nUser ORM columns:')
    for col in User.__table__.columns:
        print(' ', col.name, '->', col.type)
