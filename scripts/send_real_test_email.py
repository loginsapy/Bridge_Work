import sys
sys.path.insert(0, r'c:\Users\david\Proyectos\BridgeWork-Recuperar')
from app import create_app, db
from app.models import User, Project, Task, SystemSettings
from app.services.notifications import NotificationService

app = create_app()
with app.app_context():
    # Find a client with a non-example email
    client_user = User.query.filter(User.is_internal == False).filter(~User.email.ilike('%example.com%')).first()
    if not client_user:
        client_user = User.query.filter_by(is_internal=False).first()
    if not client_user:
        print('No client user found to send test email to. Aborting.')
        sys.exit(2)

    # Ensure SMTP config looks present
    smtp_ok = bool(SystemSettings.get('smtp_host')) and bool(SystemSettings.get('email_from'))
    print('SMTP configured:', smtp_ok)
    print('Target client:', client_user.id, client_user.email)

    # Create a temporary project and task
    project = Project.query.filter_by(name='Real Email Test Project').first()
    if not project:
        project = Project(name='Real Email Test Project')
        db.session.add(project)
        db.session.commit()

    t = Task(title='Real Email Test Task', project_id=project.id, status='BACKLOG')
    t.assigned_client_id = client_user.id
    db.session.add(t)
    db.session.commit()
    print('Created task', t.id)

    # Use an internal user as assigned_by if present
    internal = User.query.filter_by(is_internal=True).first()

    print('Triggering NotificationService.notify_task_assigned with send_email=True')

    res = NotificationService.notify_task_assigned(task=t, assigned_by_user=internal, send_email=True, notify_client=True)
    print('Result:', res)
    print('If email was sent, SMTP server logs above should show send attempt and success/failure.')
