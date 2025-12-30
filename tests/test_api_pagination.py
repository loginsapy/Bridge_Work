def test_projects_pagination(client, db, create_project):
    # create 25 projects
    for i in range(25):
        create_project(name=f'P{i}')

    rv = client.get('/api/projects?page=1&per_page=10')
    assert rv.status_code == 200
    data = rv.get_json()
    assert 'items' in data and 'meta' in data
    assert len(data['items']) == 10
    assert data['meta']['total'] == 25

    rv = client.get('/api/projects?page=3&per_page=10')
    data = rv.get_json()
    assert len(data['items']) == 5


def test_tasks_filter_by_project(client, db, create_project, create_task):
    p1 = create_project(name='PF1')
    p2 = create_project(name='PF2')
    create_task(project_id=p1['id'], title='t1', is_external_visible=True)
    create_task(project_id=p2['id'], title='t2', is_external_visible=True)

    rv = client.get(f"/api/tasks?project_id={p1['id']}")
    data = rv.get_json()
    assert data['meta']['total'] == 1
    assert data['items'][0]['project_id'] == p1['id']


def test_time_entries_filter_by_user(client, db, create_project, create_task, create_user):
    p = create_project(name='TP1')
    t = create_task(project_id=p['id'], title='te1', is_external_visible=True)
    u1 = create_user(email='a@example.com')
    u2 = create_user(email='b@example.com')
    client.post('/api/time_entries', json={"task_id": t['id'], "user_id": u1.id, "date": "2025-12-22", "hours": 1})
    client.post('/api/time_entries', json={"task_id": t['id'], "user_id": u2.id, "date": "2025-12-22", "hours": 2})

    rv = client.get(f"/api/time_entries?user_id={u1.id}")
    data = rv.get_json()
    assert data['meta']['total'] == 1
    assert data['items'][0]['user_id'] == u1.id
