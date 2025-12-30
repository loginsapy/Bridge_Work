def test_task_reorder_endpoint(client, db, create_project, create_task, create_user, login):
    u = create_user(email='reorder@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-reorder')
    t1 = create_task(project_id=p['id'], title='T1')
    t2 = create_task(project_id=p['id'], title='T2')
    t3 = create_task(project_id=p['id'], title='T3')

    # New order T3, T1, T2
    rv = client.post(f"/project/{p['id']}/tasks/reorder", json={'ordered_task_ids': [t3['id'], t1['id'], t2['id']]})
    assert rv.status_code == 200
    from app.models import Task
    t1o = Task.query.get(t1['id'])
    t2o = Task.query.get(t2['id'])
    t3o = Task.query.get(t3['id'])
    assert t3o.position == 0
    assert t1o.position == 1
    assert t2o.position == 2


def test_task_reorder_requires_internal(client, db, create_project, create_task, create_user, login):
    # create a non-internal user
    u = create_user(email='user@example.com', is_internal=False)
    login(u)
    p = create_project(name='P-reorder-2')
    t1 = create_task(project_id=p['id'], title='T1')

    rv = client.post(f"/project/{p['id']}/tasks/reorder", json={'ordered_task_ids': [t1['id']]})
    assert rv.status_code == 403
