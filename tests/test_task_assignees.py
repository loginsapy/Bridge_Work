def test_assign_multiple_users_to_task(client, create_user, login, create_project, create_task):
    # Create two internal users
    u1 = create_user(email='a@example.com', is_internal=True, first_name='Alice')
    u2 = create_user(email='b@example.com', is_internal=True, first_name='Bob')

    # Login as u1 to perform API calls
    login(u1)

    # Create a project and a task via API
    p = create_project(name='PTaskAssign', via_api=True)
    t = create_task(project_id=p['id'], title='TaskAssign', via_api=True)

    # Assign both users
    rv = client.patch(f"/api/tasks/{t['id']}", json={'assignees': [u1.id, u2.id]})
    assert rv.status_code == 200

    # Verify assignees on GET
    rv2 = client.get(f"/api/tasks/{t['id']}")
    data = rv2.get_json()
    assert 'assignees' in data
    assert set(data['assignees']) == set([u1.id, u2.id])


def test_assign_multiple_users_via_form(client, create_user, login, create_project):
    # Create two internal users
    u1 = create_user(email='form_a@example.com', is_internal=True, first_name='FormA')
    u2 = create_user(email='form_b@example.com', is_internal=True, first_name='FormB')

    # Login as u1 to perform creation
    login(u1)

    # Create project
    p = create_project(name='PFormAssign', via_api=False)

    # Submit form to create task with multiple assignees
    rv = client.post('/task', data={
        'project_id': p['id'],
        'title': 'TaskFormAssign',
        'assignees': [str(u1.id), str(u2.id)]
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Tarea' in rv.data

    # Fetch tasks via API to verify assignees
    rv2 = client.get(f"/api/tasks?project_id={p['id']}")
    data = rv2.get_json()
    items = data.get('items', [])
    assert len(items) >= 1
    # Find task with matching title
    found = None
    for t in items:
        if t.get('title') == 'TaskFormAssign':
            found = t
            break
    assert found is not None
    rv3 = client.get(f"/api/tasks/{found['id']}")
    td = rv3.get_json()
    assert 'assignees' in td
    assert set(td['assignees']) >= set([u1.id, u2.id])


def test_edit_assign_multiple_via_form(client, create_user, login, create_project, create_task):
    # Create two internal users
    u1 = create_user(email='edit_a@example.com', is_internal=True, first_name='EditA')
    u2 = create_user(email='edit_b@example.com', is_internal=True, first_name='EditB')

    # Login as u1 to perform edit
    login(u1)

    # Create project and task locally (not via API)
    p = create_project(name='PEditAssign', via_api=False)
    t = create_task(project_id=p['id'], title='TaskEditAssign', via_api=False)

    # Submit edit form to assign both users
    # Send multiple assignees as separate form fields to simulate checkboxes
    from werkzeug.datastructures import MultiDict
    form_data = MultiDict([
        ('title', t['title']),
        ('assignees', str(u1.id)),
        ('assignees', str(u2.id)),
    ])
    rv = client.post(f"/task/{t['id']}/edit", data=form_data, follow_redirects=True, content_type='multipart/form-data')
    assert rv.status_code == 200
    if b'Tarea actualizada.' not in rv.data:
        print('\n---- Edit response snippet ----')
        print(rv.data.decode()[:15000])
        print('\n---- end snippet ----')
        # Debug: inspect DB Task.assignees directly
        from app.models import Task as TaskModel
        with client.application.app_context():
            tdb = TaskModel.query.get(t['id'])
            print('DB assignees after POST:', [u.id for u in (tdb.assignees or [])])
    assert b'Tarea actualizada.' in rv.data

    # Verify via API
    rv2 = client.get(f"/api/tasks/{t['id']}")
    data = rv2.get_json()
    assert 'assignees' in data
    assert set(data['assignees']) >= set([u1.id, u2.id])
