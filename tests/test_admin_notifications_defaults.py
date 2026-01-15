def test_admin_notifications_defaults_on(client, db, create_user, login):
    # Ensure admin page shows notification toggles on by default
    from app.models import Role
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()

    admin = create_user(email='defaults_admin@example.com', is_internal=True)
    admin.role = role
    db.session.commit()

    login(admin)
    rv = client.get('/admin/settings')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Check some key notification toggles are present and checked by default
    assert 'name="notify_task_assigned"' in html
    assert 'name="notify_task_assigned"' in html and 'checked' in html.split('name="notify_task_assigned"',1)[1][:100]

    assert 'name="notify_task_completed"' in html
    assert 'name="notify_task_completed"' in html and 'checked' in html.split('name="notify_task_completed"',1)[1][:100]

    assert 'name="notify_task_approved"' in html
    assert 'name="notify_task_approved"' in html and 'checked' in html.split('name="notify_task_approved"',1)[1][:100]

    assert 'name="notify_task_rejected"' in html
    assert 'name="notify_task_rejected"' in html and 'checked' in html.split('name="notify_task_rejected"',1)[1][:100]

    assert 'name="notify_task_comment"' in html
    assert 'name="notify_task_comment"' in html and 'checked' in html.split('name="notify_task_comment"',1)[1][:100]

    assert 'name="notify_due_date_reminder"' in html
    assert 'name="notify_due_date_reminder"' in html and 'checked' in html.split('name="notify_due_date_reminder"',1)[1][:100]
