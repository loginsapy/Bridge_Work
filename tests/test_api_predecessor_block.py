def test_api_prevent_complete_when_predecessors_incomplete(client, db, create_project, create_task, create_user, login):
    # Setup
    u = create_user(email='u1@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-api')
    t1 = create_task(project_id=p['id'], title='API-T1')
    t2 = create_task(project_id=p['id'], title='API-T2')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    # Attempt to mark t2 as done via API
    rv = client.patch(f"/api/tasks/{t2_obj.id}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_predecessors' in j
    assert isinstance(j['incomplete_predecessors'], list)
    assert j['incomplete_predecessors'][0]['id'] == t1_obj.id


def test_api_prevent_complete_when_has_incomplete_descendants(client, db, create_project, create_task, create_user, login):
    # Setup
    u = create_user(email='u2@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-desc')
    t1 = create_task(project_id=p['id'], title='Parent API')
    t2 = create_task(project_id=p['id'], title='Child API')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Make child depend on parent (parent -> child)
    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    # Attempt to mark parent as done via API (should be blocked due to incomplete descendant)
    rv = client.patch(f"/api/tasks/{t1_obj.id}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_descendants' in j
    assert isinstance(j['incomplete_descendants'], list)
    assert j['incomplete_descendants'][0]['id'] == t2_obj.id


def test_api_prevent_complete_when_child_has_parent_link(client, db, create_project, create_task, create_user, login):
    # Setup
    u = create_user(email='u4@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-child')
    parent = create_task(project_id=p['id'], title='Top')
    child = create_task(project_id=p['id'], title='Sub', parent_task_id=parent['id'])

    from app.models import Task, db as _db
    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # Attempt to mark parent as done via API (should be blocked due to incomplete child)
    rv = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_descendants' in j
    assert isinstance(j['incomplete_descendants'], list)
    assert j['incomplete_descendants'][0]['id'] == child_obj.id


def test_api_prevent_complete_when_has_hierarchical_children(client, db, create_project, create_task, create_user, login):
    # Setup
    u = create_user(email='u3@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-hier')
    parent = create_task(project_id=p['id'], title='Parent H')
    child = create_task(project_id=p['id'], title='Child H', parent_task_id=parent['id'])

    from app.models import Task, db as _db
    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # Attempt to mark parent as done via API (should be blocked due to incomplete child)
    rv = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_descendants' in j
    assert isinstance(j['incomplete_descendants'], list)
    assert j['incomplete_descendants'][0]['id'] == child_obj.id

