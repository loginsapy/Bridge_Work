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
        # Create or reuse roles
        participante = Role.query.filter_by(name='Participante').first()
        if not participante:
            participante = Role(name='Participante')
            db.session.add(participante)
        pmp = Role.query.filter_by(name='PMP').first()
        if not pmp:
            pmp = Role(name='PMP')
            db.session.add(pmp)
        db.session.commit()

        # Create or reuse participante user
        u = User.query.filter_by(email='part@example.com').first()
        if not u:
            u = User(email='part@example.com', first_name='Part', is_internal=True)
            u.set_password('password')
            u.role = participante
            db.session.add(u)
            db.session.commit()
        else:
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
        # ensure role exists
        pmp_role = Role.query.filter_by(name='PMP').first()
        if not pmp_role:
            pmp_role = Role(name='PMP')
            db.session.add(pmp_role)
            db.session.commit()

        # Create or reuse pmp user
        u = User.query.filter_by(email='pmp@example.com').first()
        if not u:
            u = User(email='pmp@example.com', first_name='PM', is_internal=True)
            u.set_password('password')
            u.role = pmp_role
            db.session.add(u)
            db.session.commit()
        else:
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


def test_participant_case_insensitive():
    os.environ['DATABASE_URL'] = 'sqlite:///test_roles.db'
    if os.path.exists('test_roles.db'):
        os.remove('test_roles.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        # Create or reuse roles (robust against existing entries)
        participante = Role.query.filter_by(name='participante').first()
        if not participante:
            participante = Role(name='participante')
            db.session.add(participante)
        pmp = Role.query.filter_by(name='PMP').first()
        if not pmp:
            pmp = Role(name='PMP')
            db.session.add(pmp)
        db.session.commit()

        # Create or reuse participante user
        u = User.query.filter_by(email='part2@example.com').first()
        if not u:
            u = User(email='part2@example.com', first_name='Part2', is_internal=True)
            u.set_password('password')
            u.role = participante
            db.session.add(u)
            db.session.commit()
        else:
            u.set_password('password')
            u.role = participante
            db.session.add(u)
            db.session.commit()

    client = app.test_client()

    # Login as participante
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'part2@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    # Fetch dashboard
    dashboard = client.get('/')
    html = dashboard.get_data(as_text=True)

    # Ensure the Spanish translation for budget_used is NOT shown
    assert 'Presupuesto usado' not in html


def test_client_does_not_see_budget_card():
    os.environ['DATABASE_URL'] = 'sqlite:///test_roles.db'
    if os.path.exists('test_roles.db'):
        os.remove('test_roles.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        cliente = Role.query.filter_by(name='Cliente').first()
        if not cliente:
            cliente = Role(name='Cliente')
            db.session.add(cliente)
        pmp = Role.query.filter_by(name='PMP').first()
        if not pmp:
            pmp = Role(name='PMP')
            db.session.add(pmp)
        db.session.commit()

        # Create or reuse cliente user
        u = User.query.filter_by(email='client_user@example.com').first()
        if not u:
            u = User(email='client_user@example.com', first_name='Client', is_internal=False)
            u.set_password('password')
            u.role = cliente
            db.session.add(u)
            db.session.commit()
        else:
            u.set_password('password')
            u.role = cliente
            db.session.add(u)
            db.session.commit()

    client = app.test_client()

    # Login as cliente
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'client_user@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    # Fetch dashboard
    dashboard = client.get('/')
    html = dashboard.get_data(as_text=True)

    # Ensure the Spanish translation for budget_used is NOT shown for clients
    assert 'Presupuesto usado' not in html


def test_team_cards_visibility_by_role():
    os.environ['DATABASE_URL'] = 'sqlite:///test_roles.db'
    if os.path.exists('test_roles.db'):
        os.remove('test_roles.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        # Ensure roles exist
        pmp = Role.query.filter_by(name='PMP').first()
        if not pmp:
            pmp = Role(name='PMP')
            db.session.add(pmp)
        admin = Role.query.filter_by(name='Admin').first()
        if not admin:
            admin = Role(name='Admin')
            db.session.add(admin)
        participante = Role.query.filter_by(name='Participante').first()
        if not participante:
            participante = Role(name='Participante')
            db.session.add(participante)
        cliente = Role.query.filter_by(name='Cliente').first()
        if not cliente:
            cliente = Role(name='Cliente')
            db.session.add(cliente)
        db.session.commit()

        # Create users for each role
        def ensure_user(email, role, is_internal=True):
            u = User.query.filter_by(email=email).first()
            if not u:
                u = User(email=email, first_name=email.split('@')[0], is_internal=is_internal)
                u.set_password('password')
                u.role = role
                db.session.add(u)
                db.session.commit()
            else:
                u.set_password('password')
                u.role = role
                db.session.add(u)
                db.session.commit()
            return u

        u_pmp = ensure_user('pmp2@example.com', pmp, True)
        u_admin = ensure_user('admin@example.com', admin, True)
        u_part = ensure_user('part3@example.com', participante, True)
        u_client = ensure_user('client2@example.com', cliente, False)

    client = app.test_client()

    # helper to login and fetch dashboard html
    def dashboard_html_for(email):
        resp = client.post('/auth/login', data={'action': 'local', 'email': email, 'password': 'password'}, follow_redirects=True)
        assert resp.status_code == 200
        return client.get('/').get_data(as_text=True)

    # PMP sees team cards
    html = dashboard_html_for('pmp2@example.com')
    assert 'Velocidad del Equipo' in html
    assert 'Equipo con Actividad Reciente' in html

    # Admin sees team cards
    html = dashboard_html_for('admin@example.com')
    assert 'Velocidad del Equipo' in html
    assert 'Equipo con Actividad Reciente' in html

    # Participant does NOT see team cards
    html = dashboard_html_for('part3@example.com')
    assert 'Velocidad del Equipo' not in html
    assert 'Equipo con Actividad Reciente' not in html

    # Client does NOT see team cards
    html = dashboard_html_for('client2@example.com')
    assert 'Velocidad del Equipo' not in html
    assert 'Equipo con Actividad Reciente' not in html
