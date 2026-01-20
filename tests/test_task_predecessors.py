def test_predecessor_cycle_detection(db, create_project, create_task):
    # Create a project and two tasks
    project = create_project(name='P-Cycle')
    t1 = create_task(project_id=project['id'], title='T1')
    t2 = create_task(project_id=project['id'], title='T2')

    from app.models import Task, db as _db

    # Reload tasks as model instances
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Set t1 as predecessor of t2 (t1 -> t2)
    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    # Now attempting to set t2 as predecessor of t1 should raise ValueError (creates a cycle)
    try:
        t1_obj.validate_predecessor_ids([t2_obj.id])
        assert False, "Expected ValueError when creating cycle, but validation passed"
    except ValueError as e:
        assert 'cycle' in str(e).lower()


def test_predecessor_project_validation(db, create_project, create_task):
    p1 = create_project(name='P1')
    p2 = create_project(name='P2')
    t1 = create_task(project_id=p1['id'], title='P1-T1')
    t2 = create_task(project_id=p2['id'], title='P2-T1')

    from app.models import Task
    t1_obj = Task.query.get(t1['id'])

    try:
        t1_obj.validate_predecessor_ids([t2['id']])
        assert False, "Expected ValueError for cross-project predecessor"
    except ValueError as e:
        assert 'different project' in str(e).lower()


def test_mark_complete_blocks_if_predecessors_incomplete(client, db, create_user, create_project, create_task, login):
    # Create internal user and login
    u = create_user(email='u1@example.com', is_internal=True)
    login(u)

    p = create_project(name='P-block')
    t1 = create_task(project_id=p['id'], title='T1')
    t2 = create_task(project_id=p['id'], title='T2')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Set t1 as predecessor of t2
    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    # Attempt to mark t2 as done via route
    rv = client.post(f"/task/{t2_obj.id}/status", data={'status': 'DONE'})
    assert rv.status_code == 400
    assert b'predecesoras' in rv.data or b'incomplete_predecessors' in rv.data


def test_advance_to_in_progress_blocks_if_predecessors_incomplete(client, db, create_user, create_project, create_task, login):
    """Test that a task cannot advance to IN_PROGRESS if predecessors are incomplete."""
    u = create_user(email='advance_test@example.com', is_internal=True)
    login(u)

    p = create_project(name='P-advance')
    t1 = create_task(project_id=p['id'], title='Predecessor')
    t2 = create_task(project_id=p['id'], title='Dependent')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Set t1 as predecessor of t2
    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    # Attempt to move t2 to IN_PROGRESS (should fail)
    rv = client.post(f"/task/{t2_obj.id}/move", 
                     json={'status': 'IN_PROGRESS'},
                     content_type='application/json')
    assert rv.status_code == 400
    data = rv.get_json()
    assert 'predecesoras' in data.get('error', '').lower()

    # Verify task is still in BACKLOG
    t2_obj = db.session.get(Task, t2['id'])
    assert t2_obj.status == 'BACKLOG'

    # Now complete the predecessor
    t1_obj = db.session.get(Task, t1['id'])
    t1_obj.status = 'COMPLETED'
    _db.session.commit()

    # Now t2 should be able to advance
    rv = client.post(f"/task/{t2_obj.id}/move", 
                     json={'status': 'IN_PROGRESS'},
                     content_type='application/json')
    assert rv.status_code == 200 or rv.status_code == 302

    t2_obj = db.session.get(Task, t2['id'])
    assert t2_obj.status == 'IN_PROGRESS'


def test_edit_task_blocks_if_predecessor_added_and_status_set(client, db, create_user, create_project, create_task, login):
    """If a user adds a predecessor and attempts to set status to COMPLETED in the same edit, it should be blocked."""
    u = create_user(email='edit_block2@example.com', is_internal=True)
    login(u)

    p = create_project(name='P-edit-block')
    t1 = create_task(project_id=p['id'], title='Pred')
    t2 = create_task(project_id=p['id'], title='ToEdit')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Attempt to edit t2: add t1 as predecessor and set status to COMPLETED
    rv = client.post(f"/task/{t2_obj.id}/edit", data={
        'title': t2_obj.title,
        'status': 'COMPLETED',
        'predecessor_ids': str(t1_obj.id)
    }, follow_redirects=True)

    # Save should not have allowed completion
    t2_obj = _db.session.get(Task, t2_obj.id)
    assert t2_obj.status != 'COMPLETED'
    # Page should contain an error mentioning predecessors
    assert b'predecesoras' in rv.data or b'No se puede avanzar la tarea' in rv.data or b'predecessor' in rv.data.lower()

