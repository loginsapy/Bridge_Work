import os
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from app import db
app = create_app()
with app.app_context():
    print('SQLALCHEMY_DATABASE_URI=', app.config.get('SQLALCHEMY_DATABASE_URI'))
    try:
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print('Tables in DB:', tables)
    except Exception as e:
        print('Error inspecting DB:', repr(e))
