import sys
sys.path.insert(0, r'c:\Users\david\Proyectos\BridgeWork-Recuperar')
from app import create_app, db
from app.models import User, Project, Task, SystemSettings
from flask import session

class FakeProvider:
    def __init__(self):
        self.sent = []
    def send_email(self, recipient_id, subject, body, html=None):
        print(f"FakeProvider: send_email called -> recipient_id={recipient_id}, subject={subject}")
        self.sent.append((recipient_id, subject))
        return True

app = create_app()
with app.app_context():
    # Ensure settings allow notifications
    SystemSettings.set('notify_task_assigned', 'true')

    # Create admin and client users if missing
    admin = User.query.filter_by(email='e2e_admin@example.com').first()
    if not admin:
        admin = User(email='e2e_admin@example.com', first_name='Admin', is_internal=True)
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()

    client_user = User.query.filter_by(email='e2e_client@example.com').first()
    if not client_user:
        client_user = User(email='e2e_client@example.com', first_name='Client', is_internal=False)
        db.session.add(client_user)
        db.session.commit()

    # Create project and attach client
    project = Project.query.filter_by(name='E2E Project').first()
    if not project:
        project = Project(name='E2E Project')
        db.session.add(project)
        db.session.commit()
    if client_user not in project.clients:
        project.clients.append(client_user)
        db.session.commit()

    # Create task without assigned client
    task = Task.query.filter_by(title='E2E Task Assign').first()
    if not task:
        task = Task(project_id=project.id, title='E2E Task Assign', status='BACKLOG')
        db.session.add(task)
        db.session.commit()

    # Start test client
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True

    # Monkeypatch provider getter to return FakeProvider instance
    from app.notifications import provider as provmod
    fake = FakeProvider()
    provmod.get_provider = lambda app=None: fake

    # Do the PATCH via API to set assigned_client_id
    rv = client.patch(f"/api/tasks/{task.id}", json={'assigned_client_id': client_user.id})
    print('PATCH status:', rv.status_code)
    print('Response:', rv.get_json())

    # Check fake provider for a sent email
    if fake.sent:
        print('E2E result: email sent to:', fake.sent)
        sys.exit(0)
    else:
        print('E2E result: NO email sent')
        sys.exit(2)
