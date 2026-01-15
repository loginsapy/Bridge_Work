def test_edit_task_block_completion_when_children_incomplete(client, db, create_project, create_task, create_user, login):
    from app.models import Task, Role
    
    # Ensure PMP role exists
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()
    
    u = create_user(email='edit_block@example.com', is_internal=True)
    u.role_id = r.id
    db.session.commit()
    
    # Store user_id before login to avoid detached session issues
    user_id = u.id
    
    login(u)
    p = create_project('P-edit')
    parent = create_task(project_id=p['id'], title='ParentEdit')
    child = create_task(project_id=p['id'], title='ChildEdit', parent_task_id=parent['id'])

    parent_id = parent['id']
    child_id = child['id']

    # Attempt to edit parent and set status to COMPLETED
    rv = client.post(f"/task/{parent_id}/edit", data={'status': 'COMPLETED', 'title': 'ParentEdit'}, follow_redirects=True)
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)
    assert 'No se puede completar la tarea mientras existan subtareas incompletas' in data or 'subtareas incompletas' in data.lower()
    # Ensure status didn't change
    parent_obj = db.session.get(Task, parent_id)
    assert parent_obj.status != 'COMPLETED'


def test_client_accept_marks_completed(client, db, create_project, create_task, create_user, login):
    from app.models import Task, Role, Project
    
    # Setup: create a client user with role and unique email
    r = Role.query.filter_by(name='Cliente').first()
    if not r:
        r = Role(name='Cliente')
        db.session.add(r)
        db.session.commit()
    
    client_user = create_user(email='client_accept@example.com', is_internal=False)
    client_user.role_id = r.id
    db.session.commit()
    
    # Store client_user_id before login
    client_user_id = client_user.id
    
    # Create project and add client to project.clients
    p = create_project(name='P-client-accept')
    project = db.session.get(Project, p['id'])
    project.clients.append(client_user)
    db.session.commit()
    
    # Create task with client assigned
    t = create_task(project_id=p['id'], title='ClientAcceptTask', is_external_visible=True, assigned_client_id=client_user_id)
    task_id = t['id']

    # Login as client
    login(client_user_id)

    # Accept task
    rv = client.post(f"/task/{task_id}/client_accept", follow_redirects=True)
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)
    assert 'Tarea aceptada y marcada como completada.' in data or 'completada' in data.lower()

    t_obj = db.session.get(Task, task_id)
    assert t_obj.status == 'COMPLETED'
    assert t_obj.approval_status == 'APPROVED'
    assert t_obj.approved_by_id == client_user_id
