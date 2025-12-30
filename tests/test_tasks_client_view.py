def test_client_sees_only_client_assigned_tasks(client, db, create_user, create_project, create_task, login):
    # Setup
    client_user = create_user(email='viewclient@example.com', is_internal=False)
    internal_user = create_user(email='internal@example.com', is_internal=True)
    login(client_user)

    p = create_project(name='P-client-view')
    # Add client to project
    from app.models import Project, Task, db as _db
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # Create tasks: one assigned to client (not visible externally), one not, and one public visible
    t1 = create_task(project_id=p['id'], title='ClientAssigned', is_external_visible=False, assigned_client_id=client_user.id)
    t2 = create_task(project_id=p['id'], title='OtherTask', is_external_visible=False, assigned_client_id=None)
    t3 = create_task(project_id=p['id'], title='PublicVisible', is_external_visible=True, assigned_client_id=None)

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'ClientAssigned' in html
    assert 'OtherTask' not in html
    assert 'PublicVisible' in html

    # Check individual task detail access and button visibility
    rv = client.get(f"/task/{t1['id']}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Aceptar y Marcar como Completado' in html  # assigned to client -> button visible

    rv = client.get(f"/task/{t3['id']}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Aceptar y Marcar como Completado' not in html  # public but not assigned -> no button

    # Private task not assigned to client should be forbidden
    rv = client.get(f"/task/{t2['id']}")
    # Should redirect to projects or show permission denied flash (status 302 for redirect)
    assert rv.status_code in (302, 403)

    # Client can accept the task assigned to them
    rv = client.post(f"/task/{t1['id']}/client_accept", follow_redirects=True)
    assert rv.status_code == 200
    from app.models import Task
    t_obj = Task.query.get(t1['id'])
    assert t_obj.status == 'COMPLETED'
    assert t_obj.approval_status == 'APPROVED'
    assert t_obj.approved_by_id == client_user.id
    assert t_obj.approved_at is not None

    # Trying to accept a task not assigned to the client should be denied
    rv = client.post(f"/task/{t3['id']}/client_accept", follow_redirects=True)
    assert rv.status_code == 200
    # ensure status didn't change for the public task
    t_public = Task.query.get(t3['id'])
    assert t_public.status != 'COMPLETED'
