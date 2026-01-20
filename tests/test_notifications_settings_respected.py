from app.services.notifications import NotificationService
from app.models import SystemSettings


def test_notify_approved_respects_setting(client, db, create_user, monkeypatch):
    u = create_user(email='notify_approve@example.com', is_internal=True)
    calls = []

    def fake_send_email(user_id, subject, notification_type='general', context=None):
        calls.append((user_id, subject, notification_type))
        return True

    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    # When disabled, should not send
    SystemSettings.set('notify_task_approved', 'false', value_type='boolean')
    n = NotificationService.notify_task_approved(task=type('T',(object,),{'id':1,'title':'T1','assigned_to_id':u.id,'project_id':None})(), approved_by_user=None, send_email=SystemSettings.get('notify_task_approved', True))
    assert len(calls) == 0

    # Enable and it should send
    SystemSettings.set('notify_task_approved', 'true', value_type='boolean')
    n2 = NotificationService.notify_task_approved(task=type('T',(object,),{'id':2,'title':'T2','assigned_to_id':u.id,'project_id':None})(), approved_by_user=None, send_email=SystemSettings.get('notify_task_approved', True))
    assert len(calls) == 1


def test_notify_comment_respects_setting(client, db, create_user, monkeypatch):
    u = create_user(email='notify_comment@example.com', is_internal=True)
    calls = []

    def fake_send_email(user_id, subject, notification_type='general', context=None):
        calls.append((user_id, subject, notification_type))
        return True

    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    SystemSettings.set('notify_task_comment', 'false', value_type='boolean')

    # Create a comment-like notification
    NotificationService.create(user_id=u.id, title='Comentario', message='Nuevo comentario', notification_type=NotificationService.TASK_COMMENT)
    assert len(calls) == 0

    SystemSettings.set('notify_task_comment', 'true', value_type='boolean')
    NotificationService.create(user_id=u.id, title='Comentario2', message='Nuevo comentario 2', notification_type=NotificationService.TASK_COMMENT)
    assert len(calls) == 1


def test_due_soon_respects_setting(client, db, create_user, monkeypatch):
    u = create_user(email='notify_due@example.com', is_internal=True)
    calls = []
    def fake_send_email(user_id, subject, notification_type='general', context=None):
        calls.append((user_id, subject, notification_type))
        return True
    monkeypatch.setattr(NotificationService, 'send_email', staticmethod(fake_send_email))

    SystemSettings.set('notify_due_date_reminder', 'false', value_type='boolean')
    NotificationService.notify_task_due_soon(task=type('T',(object,),{'id':1,'title':'T1','assigned_to_id':u.id,'project_id':None})(), days_until_due=1, send_email=None)
    assert len(calls) == 0

    SystemSettings.set('notify_due_date_reminder', 'true', value_type='boolean')
    NotificationService.notify_task_due_soon(task=type('T',(object,),{'id':2,'title':'T2','assigned_to_id':u.id,'project_id':None})(), days_until_due=1, send_email=None)
    assert len(calls) == 1
