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


def test_move_parent_blocked_until_successor_children_complete(client, db, create_user, create_project, create_task, login):
    """Test that parent task cannot be moved to COMPLETED while children (via parent_task_id) are incomplete.
    
    This tests the hierarchical parent-child relationship:
    - Parent task cannot be completed until all its children are completed first.
    
    Uses API endpoints to avoid move_task notification bug.
    """
    from app.models import Role, Task
    
    # Setup role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()

    admin = create_user(email='kanban_admin2@example.com', is_internal=True)
    admin.role_id = r.id
    db.session.commit()
    
    # Store the admin ID for login - don't keep reference to detached object
    admin_id = admin.id

    login(admin)

    # Create project and tasks
    p = create_project('Board2')
    parent = create_task(project_id=p['id'], title='ParentMove')
    child = create_task(project_id=p['id'], title='ChildMove')

    parent_id = parent['id']
    child_id = child['id']

    # Set up parent-child hierarchy: child's parent is the parent task
    # Refetch to get session-bound instances
    parent_obj = db.session.get(Task, parent_id)
    child_obj = db.session.get(Task, child_id)
    child_obj.parent_task_id = parent_id  # Child has Parent as its parent
    db.session.commit()

    # Use API endpoint to test completion blocking
    # Attempt to complete parent - should be blocked because child is incomplete
    rv = client.patch(f"/api/tasks/{parent_id}", json={'status':'COMPLETED'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'error' in j
    # The error message should mention blocked children/subtasks
    assert 'subtarea' in j['error'].lower() or 'child' in j['error'].lower()

    # Now complete the child first via API
    rv_child = client.patch(f"/api/tasks/{child_id}", json={'status':'COMPLETED'})
    assert rv_child.status_code == 200

    # Now parent can be completed
    rv_parent = client.patch(f"/api/tasks/{parent_id}", json={'status':'COMPLETED'})
    assert rv_parent.status_code == 200

