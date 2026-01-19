def test_participant_only_sees_assigned_tasks(client, db, create_project, create_task, create_user, login):
    # Create participant and two other users
    from app.models import Role
    role = Role(name='Participante')
    db.session.add(role)
    db.session.commit()

    participant = create_user(email='part@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    other = create_user(email='other@example.com', is_internal=True)

    login(participant)
    p = create_project(name='P-vis-1')
    # Task assigned to participant
    t1 = create_task(project_id=p['id'], title='T-assigned', assigned_to_id=participant.id)
    # Task assigned to someone else
    t2 = create_task(project_id=p['id'], title='T-other', assigned_to_id=other.id)

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.data.decode()
    assert 'T-assigned' in html
    assert 'T-other' not in html


def test_client_only_sees_assigned_tasks(client, db, create_project, create_task, create_user, login):
    # Create a client user (external)
    client_user = create_user(email='clientv@example.com', is_internal=False)

    login(client_user)
    p = create_project(name='P-client-vis')
    # create two tasks, only one assigned to client
    t1 = create_task(project_id=p['id'], title='ClientTask', via_api=False)
    t2 = create_task(project_id=p['id'], title='ClientTask2', via_api=False)

    # Assign only t1 to client
    from app.models import Task
    td1 = Task.query.get(t1['id'])
    td2 = Task.query.get(t2['id'])
    td1.assigned_client_id = client_user.id
    td1.is_external_visible = True
    td2.is_external_visible = True
    db.session.commit()

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.data.decode()
    assert 'ClientTask' in html
    assert 'ClientTask2' not in html