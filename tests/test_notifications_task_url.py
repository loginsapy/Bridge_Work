from app.services.notifications import NotificationService
from app.models import SystemSettings
from app import create_app


def test_notify_task_assigned_uses_base_url(monkeypatch):
    app = create_app()
    # Setup a dummy task
    class DummyTask:
        def __init__(self, id, title, project_id=None):
            self.id = id
            self.title = title
            self.project_id = project_id
            self.assigned_client_id = 1
            self.assigned_to_id = None

    t = DummyTask(111, 'T1')

    # Fake user and send_email capture
    calls = {}
    def fake_send_email(user_id, subject, notification_type='general', context=None, notification_id=None):
        calls['context'] = context
        return True

    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    with app.app_context():
        # Set base_url
        SystemSettings.set('base_url', 'https://app.test')
        # Call notify
        NotificationService.notify_task_assigned(task=t, assigned_by_user=None, send_email=True, notify_client=True)

    assert 'context' in calls
    assert 'task_url' in calls['context']
    assert calls['context']['task_url'].startswith('https://app.test')
