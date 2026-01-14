from app.tasks.monitor import check_failed_alerts


class DummyProvider:
    def __init__(self):
        self.calls = []

    def send_email(self, recipient_id, subject, body, html=None):
        self.calls.append((recipient_id, subject, body, html))
        return True


def test_check_failed_alerts_notifies_admins_when_threshold_exceeded(monkeypatch, app, db, create_user):
    # create some failed AlertLog entries
    from app.models import AlertLog
    from datetime import datetime, timedelta

    now = datetime.now()

    for i in range(6):
        al = AlertLog(task_id=100 + i, recipient_id=1, status='FAILED', created_at=(now - timedelta(minutes=10)))
        db.session.add(al)
    # create an internal admin user
    admin = create_user(email='admin@example.com', is_internal=True)

    db.session.commit()

    provider = DummyProvider()
    import app.notifications.provider as prov_mod
    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    with app.app_context():
        res = check_failed_alerts(threshold=5, window_hours=1)

        assert res['failures'] >= 6
        # provider should have been called for admin
        assert provider.calls
        assert any(call[0] == admin.id for call in provider.calls)


def test_check_failed_alerts_does_not_notify_below_threshold(monkeypatch, app, db, create_user):
    from app.models import AlertLog
    from datetime import datetime, timedelta

    now = datetime.now()
    for i in range(3):
        al = AlertLog(task_id=200 + i, recipient_id=1, status='FAILED', created_at=(now - timedelta(minutes=10)))
        db.session.add(al)

    admin = create_user(email='admin2@example.com', is_internal=True)
    db.session.commit()

    provider = DummyProvider()
    import app.notifications.provider as prov_mod
    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: provider)

    with app.app_context():
        res = check_failed_alerts(threshold=5, window_hours=1)
        assert res['failures'] == 3
        assert provider.calls == []
