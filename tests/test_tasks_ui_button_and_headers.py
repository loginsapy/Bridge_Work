def test_tasks_new_from_project_button_and_headers(client, db, create_user, login):
    # create admin user
    admin = create_user(email='btnui@example.com', is_internal=True)
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()
    admin.role = r
    db.session.commit()

    login(admin)
    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.data.decode()
    # The new from project button exists (check for text and button class)
    from app.translations import t
    assert t('new_from_project', 'es') in html or t('new_from_project', 'en') in html
    assert 'monday-btn' in html
    # Headers are visible and more contrast (verify localized task_title)
    assert 'WBS' in html
    assert t('task_title', 'es') in html or t('task_title', 'en') in html
    # Hours header is present and should be visible
    assert t('hours', 'es') in html or t('hours', 'en') in html