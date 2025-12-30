def test_create_task_with_client_assignment(client, db, create_project, create_task, create_user, login):
    # Setup
    admin = create_user(email='admin2@example.com', is_internal=True)
    client_user = create_user(email='cust@example.com', is_internal=False)
    login(admin)
    p = create_project(name='P-clientassign')

    # Add client to project
    from app.models import Project, User, db as _db, Task
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # Create task via form with assigned_client_id
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'T-client', 'assigned_client_id': str(client_user.id)}, follow_redirects=True)
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)
    assert 'Tarea creada' in data or 'Tarea' in data

    # Verify task assigned_client_id
    t = Task.query.filter_by(title='T-client').first()
    assert t is not None
    assert t.assigned_client_id == client_user.id


def test_api_create_task_with_client_assignment(client, db, create_project, create_user, login):
    admin = create_user(email='api_admin@example.com', is_internal=True)
    client_user = create_user(email='api_client@example.com', is_internal=False)
    login(admin)
    p = create_project(name='P-api-assign')

    from app.models import Project, User, db as _db, Task
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    rv = client.post('/api/tasks', json={'project_id': p['id'], 'title': 'API-Client', 'assigned_client_id': client_user.id})
    assert rv.status_code == 201
    j = rv.get_json()
    assert j['assigned_client_id'] == client_user.id
    t = Task.query.get(j['id'])
    assert t.assigned_client_id == client_user.id
