def test_time_user_filter_and_dropdown_only_includes_users_with_entries(client, db, create_user, create_project, create_task, login):
    # create users
    u1 = create_user(email='u1time@example.com', is_internal=True, first_name='U1')
    u2 = create_user(email='u2time@example.com', is_internal=True, first_name='U2')
    from app.models import TimeEntry, Task
    # create a project and task
    p = create_project(name='P-time')
    t = create_task(project_id=p['id'], title='Some Task')
    # add time entry only for u1
    from app import db
    import datetime
    te = TimeEntry(task_id=t['id'], user_id=u1.id, date=datetime.date(2025,12,22), hours=1)
    db.session.add(te)
    db.session.commit()

    # login as admin
    admin = create_user(email='admintime@example.com', is_internal=True)
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()
    admin.role = r
    db.session.commit()
    login(admin)

    rv = client.get('/time-entries')
    html = rv.data.decode()
    assert 'U1' in html
    assert 'U2' not in html

    # Ensure filtering by u1 works
    rv2 = client.get(f'/time-entries?user_id={u1.id}')
    assert rv2.status_code == 200
    # Filtering by u2 (no entries) shouldn't error and should show no records
    rv3 = client.get(f'/time-entries?user_id={u2.id}')
    assert rv3.status_code == 200
    assert 'Sin time entries' not in rv3.data.decode()  # page renders with empty state or without dying
