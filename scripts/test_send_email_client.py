import sys
sys.path.insert(0, r'c:\Users\david\Proyectos\BridgeWork-Recuperar')
from app import create_app, db
from app.models import SystemSettings, User, Project, Task
from app.services.notifications import NotificationService
import traceback

app = create_app()
with app.app_context():
    try:
        print('smtp_host =>', SystemSettings.get('smtp_host'))
        print('smtp_port =>', SystemSettings.get('smtp_port'))
        print('smtp_username =>', SystemSettings.get('smtp_username'))
        print('smtp_use_tls =>', SystemSettings.get('smtp_use_tls'))
        print('email_from =>', SystemSettings.get('email_from'))
        print('notify_task_assigned =>', SystemSettings.get('notify_task_assigned'))

        project = Project.query.first()
        client = project.clients[0] if project and project.clients else None
        internal = User.query.filter_by(is_internal=True).first()
        print('project', project.id if project else None, 'client', client.email if client else None, 'internal', internal.email if internal else None)

        t = Task(project_id=project.id, title='NOTIF_SEND_TEST', status='BACKLOG')
        if client:
            t.assigned_client_id = client.id
        if internal:
            t.assigned_to_id = internal.id
        db.session.add(t)
        db.session.commit()
        print('Created task', t.id)

        res = NotificationService.notify_task_assigned(task=t, assigned_by_user=internal, send_email=True, notify_client=True)
        print('notify returned:', res)
    except Exception as e:
        print('exception during test send:')
        traceback.print_exc()
