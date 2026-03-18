from app.models import User, Role, Project, Task


def test_client_assigned_task_visible_and_can_approve(client, db, create_user, create_project, login):
    # Ensure Cliente role
    cliente_role = Role.query.filter_by(name='Cliente').first()
    if not cliente_role:
        cliente_role = Role(name='Cliente')
        db.session.add(cliente_role)
        db.session.commit()

    # Create client user
    client_user = create_user(email='assigned_client@example.com', is_internal=False)

    # Create project
    p = create_project(name='P-Assigned')

    # Create internal user
    internal = create_user(email='internal_pa@example.com', is_internal=True)

    # Create tasks assigned to client
    t = Task(project_id=p['id'], title='Task for client approval', status='COMPLETED',
             is_external_visible=True, requires_approval=True)
    t.assigned_client_id = client_user.id
    db.session.add(t)

    t_hidden = Task(project_id=p['id'], title='Hidden Task for client approval', status='COMPLETED',
                    is_external_visible=False, requires_approval=True)
    t_hidden.assigned_client_id = client_user.id
    db.session.add(t_hidden)
    db.session.commit()

    t_id = t.id
    t_hidden_id = t_hidden.id
    client_user_id = client_user.id

    login(client_user)

    resp = client.get('/pending-approvals')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Task for client approval' in html

    # Approve the visible task
    resp = client.post(f'/task/{t_id}/approve', data={'notes': 'Looks good'}, follow_redirects=True)
    assert resp.status_code == 200

    updated = db.session.get(Task, t_id)
    assert updated.approval_status == 'APPROVED'
    assert updated.approved_by_id == client_user_id

    # Check hidden-but-assigned task is visible for the client
    resp = client.get('/pending-approvals')
    assert 'Hidden Task for client approval' in resp.get_data(as_text=True)


def test_internal_user_cannot_access_pending_approvals(client, db, create_user, login):
    internal = create_user(email='internal_pa2@example.com', is_internal=True)
    login(internal)

    resp = client.get('/pending-approvals', follow_redirects=True)
    assert resp.status_code == 200
    assert 'Esta sección es solo para clientes.' in resp.get_data(as_text=True)
