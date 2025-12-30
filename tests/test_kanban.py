def test_move_task_changes_status(client, db, create_user, create_project, create_task, login):
    # Create PMP user and login
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()

    admin = create_user(email='kanban_admin@example.com', is_internal=True)
    admin.role_id = r.id
    db.session.commit()

    login(admin)

    p = create_project('Board1')
    t = create_task(project_id=p['id'], title='MoveMe')

    # move task to IN_PROGRESS
    rv = client.post(f"/task/{t['id']}/move", json={'status':'IN_PROGRESS'})
    assert rv.status_code == 200
    j = rv.get_json()
    assert j['status'] == 'ok'
    from app.models import Task
    with client.application.app_context():
        task = Task.query.get(t['id'])
        assert task.status == 'IN_PROGRESS'


def test_move_task_block_completion_if_descendants_incomplete(client, db, create_user, create_project, create_task, login):
    # Setup
    admin = create_user(email='kanban_admin2@example.com', is_internal=True)
    login(admin)

    p = create_project('Board2')
    parent = create_task(project_id=p['id'], title='ParentMove')
    child = create_task(project_id=p['id'], title='ChildMove')

    from app.models import Task, db as _db
    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # Make child dependent on parent (parent -> child)
    child_obj.predecessors = [parent_obj]
    _db.session.commit()

    # Attempt to move parent to COMPLETED via kanban move
    rv = client.post(f"/task/{parent_obj.id}/move", json={'status':'COMPLETED'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_children' in j
    assert isinstance(j['incomplete_children'], list)
    assert j['incomplete_children'][0]['id'] == child_obj.id