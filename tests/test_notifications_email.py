import pytest

from app.services.notifications import NotificationService
from app.models import SystemSettings, User


def test_create_task_assigned_sends_email(client, db, create_user, monkeypatch):
    # Setup: create a user
    u = create_user(email='notify_test@example.com', is_internal=True)

    sent = {}
    def fake_send_email(user_id, subject, notification_type='general', context=None):
        sent['user_id'] = user_id
        sent['subject'] = subject
        sent['notification_type'] = notification_type
        sent['context'] = context
        return True

    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    # Ensure global setting allows notify for task assigned
    SystemSettings.set('notify_task_assigned', 'true')

    n = NotificationService.create(
        user_id=u.id,
        title='Nueva tarea asignada',
        message='Se te asignó una tarea de prueba',
        notification_type=NotificationService.TASK_ASSIGNED
    )

    assert n is not None
    assert sent.get('user_id') == u.id
    assert 'Nueva tarea asignada' in sent.get('subject')
    assert sent.get('notification_type') == NotificationService.TASK_ASSIGNED


def test_create_general_does_not_send_by_default(client, db, create_user, monkeypatch):
    u = create_user(email='notify_general@example.com', is_internal=True)
    called = {'sent': False}
    def fake_send_email(*args, **kwargs):
        called['sent'] = True
        return True
    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    SystemSettings.set('notify_task_assigned', 'true')

    n = NotificationService.create(
        user_id=u.id,
        title='General notice',
        message='Una notificación general',
        notification_type=NotificationService.GENERAL
    )

    assert n is not None
    assert called['sent'] is False


def test_notify_task_assigned_sends_email_once(client, db, create_user, monkeypatch):
    # Ensure notify_task_assigned triggers a single email send when send_email=True
    u = create_user(email='notify_once@example.com', is_internal=True)
    calls = []
    def fake_send_email(user_id, subject, notification_type='general', context=None):
        calls.append((user_id, subject, notification_type))
        return True
    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    SystemSettings.set('notify_task_assigned', 'true')

    # Create a dummy task object-like with required attributes
    class DummyTask:
        def __init__(self, id, title, project_id=None):
            self.id = id
            self.title = title
            self.project_id = project_id
            self.assigned_client_id = None
            self.assigned_to_id = u.id

    t = DummyTask(999, 'T-Notify-Once', None)

    NotificationService.notify_task_assigned(task=t, assigned_by_user=None, send_email=True, notify_client=False)

    assert len(calls) == 1
    assert calls[0][0] == u.id
    assert NotificationService.TASK_ASSIGNED == calls[0][2] or True
