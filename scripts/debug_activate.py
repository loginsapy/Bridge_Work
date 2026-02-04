from app import create_app, db
from app.models import User, Role

app = create_app()
with app.app_context():
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()
    user = User.query.filter_by(email='test-admin@example.com').first()
    if not user:
        user = User(email='test-admin@example.com', is_internal=True)
        user.role = role
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True

    res = client.post('/api/license/activate', json={'license_key':'SAMPLE-KEY-1234'})
    print('status', res.status_code)
    try:
        print(res.get_json())
    except Exception:
        print(res.get_data(as_text=True))
