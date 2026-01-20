from app import create_app

app = create_app()

with app.app_context():
    from app import db
    db.create_all()
    print('OK: tables created using metadata (create_all)')
