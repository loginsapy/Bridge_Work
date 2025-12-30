from app.tasks.sender import send_grouped_alerts


class DummyProvider:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    def send_email(self, recipient_id, subject, body, html=None):
        self.calls.append((recipient_id, subject, body, html))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise Exception('temporary')
        return True


def test_send_grouped_alerts_success(monkeypatch, app):
    provider = DummyProvider()
    import app.notifications.provider as prov_mod

    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    groups = {1: [10, 11], 2: [20]}
    res = None
    with app.app_context():
        res = send_grouped_alerts(groups, retries=2, backoff_factor=0)

    assert set(res['success']) == {1, 2}
    assert res['failed'] == []
    assert len(provider.calls) == 2


def test_send_grouped_alerts_retries_and_fails(monkeypatch, app):
    # provider fails even after retries
    provider = DummyProvider(fail_times=5)
    import app.notifications.provider as prov_mod

    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    groups = {1: [10]}
    with app.app_context():
        res = send_grouped_alerts(groups, retries=3, backoff_factor=0)

    assert res['success'] == []
    assert res['failed'] == [1]
    # provider called 3 times (retries)
    assert len(provider.calls) == 3


def test_send_marks_alertlog_sent(monkeypatch, app, create_project, create_user, create_task):
    # ensure AlertLog entries are marked SENT on successful send
    provider = DummyProvider()
    import app.notifications.provider as prov_mod

    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    from datetime import datetime, timedelta
    p = create_project(name='AL1')
    u = create_user(email='sent@example.com')
    task = create_task(project_id=p['id'], title='t_sent', is_external_visible=False, due_date=(datetime.now() + timedelta(days=1)), assigned_to_id=u.id)

    from app.tasks.alerts import generate_alerts
    from app.models import AlertLog

    with app.app_context():
        res = generate_alerts(cutoff_days=2)
        groups = res['groups']
        # run sender
        send_grouped_alerts(groups, retries=1, backoff_factor=0)

        # check AlertLog
        logs = AlertLog.query.filter_by(task_id=task['id']).all()
        assert len(logs) == 1
        assert logs[0].status == 'SENT'
        assert logs[0].sent_at is not None


def test_send_marks_alertlog_failed(monkeypatch, app, create_project, create_user, create_task):
    # ensure AlertLog entries are marked FAILED when send ultimately fails
    provider = DummyProvider(fail_times=5)
    import app.notifications.provider as prov_mod

    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    from datetime import datetime, timedelta
    p = create_project(name='AL2')
    u = create_user(email='failed@example.com')
    task = create_task(project_id=p['id'], title='t_failed', is_external_visible=False, due_date=(datetime.now() + timedelta(days=1)), assigned_to_id=u.id)

    from app.tasks.alerts import generate_alerts
    from app.models import AlertLog

    with app.app_context():
        res = generate_alerts(cutoff_days=2)
        groups = res['groups']
        # run sender with only 2 retries (will fail)
        send_grouped_alerts(groups, retries=2, backoff_factor=0)

        # check AlertLog
        logs = AlertLog.query.filter_by(task_id=task['id']).all()
        assert len(logs) == 1
        assert logs[0].status == 'FAILED'
        assert logs[0].sent_at is not None