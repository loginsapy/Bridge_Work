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
    data = rv.get_json()
    assert 'wbs' in data and isinstance(data['wbs'], dict)
    from app.models import Task
    t1o = Task.query.get(t1['id'])
    t2o = Task.query.get(t2['id'])
    t3o = Task.query.get(t3['id'])
    assert t3o.position == 0
    assert t1o.position == 1
    assert t2o.position == 2
    # Ensure WBS mapping contains our tasks
    assert str(t1['id']) in data['wbs']
    assert str(t2['id']) in data['wbs']
    assert str(t3['id']) in data['wbs']

    # Render the board page and confirm WBS is reflected in HTML
    rv2 = client.get(f"/project/{p['id']}")
    assert rv2.status_code == 200
    html = rv2.data.decode()
    assert data['wbs'][str(t1['id'])] in html
    assert data['wbs'][str(t2['id'])] in html
    assert data['wbs'][str(t3['id'])] in html


def test_task_reorder_requires_internal(client, db, create_project, create_task, create_user, login):
    # create a non-internal user
    u = create_user(email='user@example.com', is_internal=False)
    login(u)
    p = create_project(name='P-reorder-2')
    t1 = create_task(project_id=p['id'], title='T1')

    rv = client.post(f"/project/{p['id']}/tasks/reorder", json={'ordered_task_ids': [t1['id']]})
    assert rv.status_code == 403


def test_task_reorder_requires_pmp_or_admin(client, db, create_project, create_task, create_user, login):
    # create an internal user but with role 'Participante' (should be forbidden)
    from app.models import Role
    role = Role(name='Participante')
    db.session.add(role)
    db.session.commit()

    u = create_user(email='participant@example.com', is_internal=True)
    # override default role (create_user sets 'PMP' by default for internal users)
    u.role = role
    db.session.commit()

    login(u)
    p = create_project(name='P-reorder-3')
    t1 = create_task(project_id=p['id'], title='T1')

    rv = client.post(f"/project/{p['id']}/tasks/reorder", json={'ordered_task_ids': [t1['id']]})
    assert rv.status_code == 403
