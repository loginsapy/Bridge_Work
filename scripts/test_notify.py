import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app, db
from app.models import Project, User, Task, SystemSettings
from app.services.notifications import NotificationService

app = create_app()
with app.app_context():
    project = Project.query.join(Project.clients).first()
    if not project:
        print('No project with client found')
        raise SystemExit(1)
    client = project.clients[0]
    internal = User.query.filter_by(is_internal=True).first()
    print('Project', project.id, 'client', client.id, client.email, 'internal', internal.id, internal.email)
    t = Task(project_id=project.id, title='Notif test', description='test', status='BACKLOG', priority='MEDIUM')
    t.assigned_client_id = client.id
    t.assigned_to_id = internal.id
    db.session.add(t)
    db.session.commit()
    print('Task created', t.id)
    send_email_setting = SystemSettings.get('notify_task_assigned', 'true')
    send_email = send_email_setting == 'true' or send_email_setting == True
    print('send_email:', send_email)
    NotificationService.notify_task_assigned(task=t, assigned_by_user=internal, send_email=send_email, notify_client=False)
    NotificationService.notify_task_assigned(task=t, assigned_by_user=internal, send_email=send_email, notify_client=True)
    print('Notifications triggered')