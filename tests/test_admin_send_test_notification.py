def test_admin_send_test_notification_endpoint(client, db, create_user, login, monkeypatch):
    admin = create_user(email='sendtest_admin@example.com', is_internal=True)
    from app.models import Role
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()
    admin.role = role
    db.session.commit()

    # monkeypatch provider to avoid external calls
    import app.notifications.provider as prov
    monkeypatch.setattr(prov.StubProvider, 'send_email', staticmethod(lambda recipient_id, subject, body, html=None: True))

    login(admin)
    rv = client.post('/admin/send-test-notification')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['success'] is True
    assert 'notification_id' in data
    assert 'email_sent' in data

    # Check DB record
    from app.models import SystemNotification
    n = SystemNotification.query.filter_by(id=data['notification_id']).first()
    assert n is not None
    assert n.user_id == admin.id