import os
from app import create_app, db
from app.models import User, Role, Project, Task


def test_client_assigned_task_visible_and_can_approve():
    os.environ['DATABASE_URL'] = 'sqlite:///test_pending.db'
    if os.path.exists('test_pending.db'):
        os.remove('test_pending.db')

    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        # Ensure Cliente role
        cliente_role = Role.query.filter_by(name='Cliente').first()
        if not cliente_role:
            cliente_role = Role(name='Cliente')
            db.session.add(cliente_role)
            db.session.commit()

        # Create client user (assigned client)
        client_user = User.query.filter_by(email='assigned_client@example.com').first()
        if not client_user:
            client_user = User(email='assigned_client@example.com', is_internal=False)
            client_user.set_password('password')
            client_user.role = cliente_role
            db.session.add(client_user)
            db.session.commit()

        # Create a project (no need to add client to project.clients)
        p = Project(name='P-Assigned', description='desc')
        db.session.add(p)
        db.session.commit()

        # Create an internal user as assignee
        internal = User.query.filter_by(email='internal@example.com').first()
        if not internal:
            internal = User(email='internal@example.com', is_internal=True)
            internal.set_password('password')
            db.session.add(internal)
            db.session.commit()

        # Create task assigned to client (visible externally)
        t = Task(project_id=p.id, title='Task for client approval', status='COMPLETED', is_external_visible=True, requires_approval=True)
        t.assigned_client_id = client_user.id
        db.session.add(t)
        db.session.commit()

        # Also create a task assigned to the client that is NOT externally visible — it should still appear for the assigned client
        t_hidden = Task(project_id=p.id, title='Hidden Task for client approval', status='COMPLETED', is_external_visible=False, requires_approval=True)
        t_hidden.assigned_client_id = client_user.id
        db.session.add(t_hidden)
        db.session.commit()

        # Capture ids while attached to session to avoid DetachedInstanceError later
        t_id = t.id
        t_hidden_id = t_hidden.id
        client_user_id = client_user.id

    client = app.test_client()

    # Login as client and see pending approvals
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'assigned_client@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    resp = client.get('/pending-approvals')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Task for client approval' in html

    # Approve the task
    # Approve the visible task
    resp = client.post(f'/task/{t_id}/approve', data={'notes': 'Looks good'}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        updated = Task.query.get(t_id)
        assert updated.approval_status == 'APPROVED'
        assert updated.approved_by_id == client_user_id

    # Check that the hidden-but-assigned task is visible in the page for the client
    resp = client.get('/pending-approvals')
    assert 'Hidden Task for client approval' in resp.get_data(as_text=True)


def test_internal_user_cannot_access_pending_approvals():
    os.environ['DATABASE_URL'] = 'sqlite:///test_pending.db'
    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    with app.app_context():
        # reuse DB
        pass

    client = app.test_client()
    # login as internal user (created earlier)
    resp = client.post('/auth/login', data={'action': 'local', 'email': 'internal@example.com', 'password': 'password'}, follow_redirects=True)
    assert resp.status_code == 200

    resp = client.get('/pending-approvals', follow_redirects=True)
    # Should redirect away from pending approvals
    assert resp.status_code == 200
    assert 'Esta sección es solo para clientes.' in resp.get_data(as_text=True)
