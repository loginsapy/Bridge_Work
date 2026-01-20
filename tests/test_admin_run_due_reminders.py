def test_admin_run_due_reminders_endpoint(client, db, create_project, create_user, create_task, login):
    admin = create_user(email='rem_admin@example.com', is_internal=True)
    login(admin)

    # Ensure reminders are enabled
    from app.models import SystemSettings
    SystemSettings.set('notify_due_date_reminder', 'true', category='notifications')
    SystemSettings.set('due_date_reminder_days', '2', category='notifications')
    db.session.commit()

    p = create_project(name='RemP')
    u = create_user(email='rem_user@example.com')
    import datetime
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1))
    create_task(project_id=p['id'], title='due', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)

    rv = client.post('/admin/run-due-reminders')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['success'] is True
    assert data['created'] == 1
    assert str(u.id) in map(str, data.get('groups', {}).keys()) or u.id in data.get('groups', {})
