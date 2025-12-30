import os
from app import create_app, db
from app.models import User, Role


def test_participant_does_not_see_budget_card(monkeypatch):
    os.environ['DATABASE_URL'] = 'sqlite:///test_roles.db'
    if os.path.exists('test_roles.db'):
        os.remove('test_roles.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        # Create roles
        participante = Role(name='Participante')
        pmp = Role(name='PMP')
        db.session.add_all([participante, pmp])
        db.session.commit()

        # Create participante user
        u = User(email='part@example.com', first_name='Part', is_internal=True)
        u.set_password('password')
        u.role = participante
        db.session.add(u)
        db.session.commit()

    client = app.test_client()

    # Login as participante
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'part@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    # Fetch dashboard
    dashboard = client.get('/')
    html = dashboard.get_data(as_text=True)

    # Spanish translation for budget_used is present in template; ensure it's NOT shown
    assert 'Presupuesto usado' not in html


def test_pmp_sees_budget_card():
    os.environ['DATABASE_URL'] = 'sqlite:///test_roles.db'
    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        # assume roles exist
        pmp_role = Role.query.filter_by(name='PMP').first()
        if not pmp_role:
            pmp_role = Role(name='PMP')
            db.session.add(pmp_role)
            db.session.commit()

        # Create pmp user
        u = User(email='pmp@example.com', first_name='PM', is_internal=True)
        u.set_password('password')
        u.role = pmp_role
        db.session.add(u)
        db.session.commit()

    client = app.test_client()
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'pmp@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    dashboard = client.get('/')
    html = dashboard.get_data(as_text=True)
    assert 'Presupuesto usado' in html
