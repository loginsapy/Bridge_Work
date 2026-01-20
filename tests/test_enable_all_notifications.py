def test_enable_all_notifications_endpoint(client, db, create_user, login):
    admin = create_user(email='enable_admin@example.com', is_internal=True)
    # grant admin role if needed
    from app.models import Role
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()
    admin.role = role
    db.session.commit()

    login(admin)
    rv = client.post('/admin/enable-all-notifications')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['success'] is True
    assert 'notify_task_assigned' in data['enabled']

    # verify settings persisted
    from app.models import SystemSettings
    for k in data['enabled']:
        s = SystemSettings.query.filter_by(key=k).first()
        assert s is not None
        assert s.value.lower() == 'true'