from app import create_app, db
import os

os.environ['DATABASE_URL'] = 'sqlite:///test.db'
app = create_app('config.DevConfig')
from sqlalchemy import text
with app.app_context():
    db.create_all()
    with db.engine.connect() as conn:
        res = conn.execute(text("PRAGMA table_info('users')")).fetchall()
        print('users table info:', res)
        res2 = conn.execute(text("SELECT sql FROM sqlite_master WHERE tbl_name = 'users'"))
        print('users create SQL:', res2.fetchall())

    from app.models import User
    print('User.__table__.columns[id].type:', User.__table__.columns['id'].type)
    for col in User.__table__.columns:
        print(col.name, '->', col.type)
