import os
from app import create_app, db
from app.models import User, Role, Project


def test_add_members_to_project(monkeypatch):
    os.environ['DATABASE_URL'] = 'sqlite:///test_project_members.db'
    if os.path.exists('test_project_members.db'):
        os.remove('test_project_members.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        # Create roles
        part = Role(name='Participante')
        pmp = Role(name='PMP')
        db.session.add_all([part, pmp])
        db.session.commit()

        # Create users
        u1 = User(email='u1@example.com', first_name='One', is_internal=True)
        u1.set_password('password')
        u1.role = part
        u2 = User(email='u2@example.com', first_name='Two', is_internal=True)
        u2.set_password('password')
        u2.role = part
        admin = User(email='admin@example.com', first_name='Admin', is_internal=True)
        admin.set_password('password')
        admin.role = pmp
        db.session.add_all([u1, u2, admin])
        db.session.commit()

        # Create a project
        p = Project(name='Test Project')
        db.session.add(p)
        db.session.commit()

    client = app.test_client()

    # Login as admin to edit
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'admin@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    # Add members u1 and u2 to the project
    resp = client.post(f'/project/{p.id}/edit', data={'name': p.name, 'member_ids': [str(u1.id), str(u2.id)]}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        proj = Project.query.get(p.id)
        member_emails = {m.email for m in proj.members}
        assert 'u1@example.com' in member_emails
        assert 'u2@example.com' in member_emails
