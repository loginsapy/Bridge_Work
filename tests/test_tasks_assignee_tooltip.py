def test_assignee_avatar_has_title(client, db, create_project, create_task, create_user, login):
    # Setup
    internal_user = create_user(email='assignee@example.com', first_name='Alice', last_name='Smith', is_internal=True)
    login(internal_user)
    p = create_project(name='P-tooltip')

    # Create a task assigned to that user
    from app.models import Task
    t = create_task(project_id=p['id'], title='TooltipTask', assigned_to_id=internal_user.id)

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    # The avatar should include a title attribute with the user's full name
    assert 'title="Alice Smith"' in html or 'title="assignee@example.com"' in html


def test_pmp_avatar_links_to_profile(client, db, create_project, create_task, create_user, login):
    # Setup PMP user
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()

    pmp = create_user(email='pmp@example.com', is_internal=True)
    pmp.role_id = r.id
    db.session.commit()

    # Assignee
    assignee = create_user(email='assignee2@example.com', first_name='Bob', last_name='Jones', is_internal=True)

    # Create project and task
    p = create_project(name='P-link')
    t = create_task(project_id=p['id'], title='LinkTask', assigned_to_id=assignee.id)

    login(pmp)
    rv = client.get('/tasks')
    html = rv.get_data(as_text=True)
    assert f'href="/user/{assignee.id}"' in html or f"url_for('main.user_profile', user_id={assignee.id})" in html


def test_admin_avatar_links_to_profile(client, db, create_project, create_task, create_user, login):
    # Setup Admin user
    from app.models import Role
    r = Role.query.filter_by(name='Admin').first()
    if not r:
        r = Role(name='Admin')
        db.session.add(r)
        db.session.commit()

    admin = create_user(email='admin@example.com', is_internal=True)
    admin.role_id = r.id
    db.session.commit()

    # Assignee
    assignee = create_user(email='assignee3@example.com', first_name='Carol', last_name='Lee', is_internal=True)

    # Create project and task
    p = create_project(name='P-link-admin')
    t = create_task(project_id=p['id'], title='LinkTaskAdmin', assigned_to_id=assignee.id)

    login(admin)
    rv = client.get('/tasks')
    html = rv.get_data(as_text=True)
    assert f'href="/user/{assignee.id}"' in html or f"url_for('main.user_profile', user_id={assignee.id})" in html
