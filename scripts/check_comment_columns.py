from app import create_app
from app import db
from sqlalchemy import inspect
import json

app = create_app()
with app.app_context():
    insp = inspect(db.engine)
    cols = insp.get_columns('task_comments')
    print(json.dumps([c['name'] for c in cols], indent=2))
