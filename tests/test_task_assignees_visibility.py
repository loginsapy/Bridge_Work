def test_participant_sees_task_assigned_via_assignees(client, db, create_project, create_task, create_user, login):
    # Create role 'Participante'
    from app.models import Role, Task
    role = Role(name='Participante')
    db.session.add(role)
    db.session.commit()

    # Create participant user and make sure role is 'Participante'
    participant = create_user(email='multiview@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    # Create project and task, assign task via many-to-many (assignees)
    p = create_project(name='P-multi-view')
    t = create_task(project_id=p['id'], title='MultiAssigned')

    # Attach participant as assignee (but leave assigned_to_id None)
    from app.models import Task as TaskModel, User
    task_db = TaskModel.query.get(t['id'])
    user_db = User.query.get(participant.id)
    task_db.assignees.append(user_db)
    task_db.assigned_to_id = None
    db.session.commit()

    # Login as participant and load board
    login(participant)
    rv = client.get(f"/project/{p['id']}")
    assert rv.status_code == 200
    assert b'MultiAssigned' in rv.data