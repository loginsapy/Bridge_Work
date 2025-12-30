def test_external_user_cannot_see_private_task(client, db, create_user, create_project, create_task, login):
    # create project and private task
    p = create_project(name='V1')
    # create an internal user to create the private task
    creator = create_user(email='creator@example.com', is_internal=True)
    # create task directly in DB to avoid API auth for setup
    t = create_task(project_id=p['id'], title='private task', is_external_visible=False, via_api=False)

    # now create external user and login as them
    u = create_user(email='ext@example.com', is_internal=False)
    login(u)

    rv = client.get(f"/api/tasks?project_id={p['id']}")
    data = rv.get_json()
    assert data['meta']['total'] == 0

    # direct GET should be forbidden
    rv = client.get(f"/api/tasks/{t['id']}")
    assert rv.status_code == 403


def test_client_sees_visible_and_assigned_tasks_api(client, db, create_user, create_project, create_task, login):
    # Create project and tasks
    p = create_project(name='V-client-api')
    client_user = create_user(email='clientapi@example.com', is_internal=False)
    # add client to project
    from app.models import Project, db as _db
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    public = create_task(project_id=p['id'], title='public2', is_external_visible=True, via_api=False)
    assigned = create_task(project_id=p['id'], title='assigned_to_client', is_external_visible=False, assigned_client_id=client_user.id, via_api=False)
    private = create_task(project_id=p['id'], title='private_no', is_external_visible=False, assigned_client_id=None, via_api=False)

    login(client_user)

    rv = client.get(f"/api/tasks?project_id={p['id']}")
    data = rv.get_json()
    assert data['meta']['total'] == 2
    titles = {it['title'] for it in data['items']}
    assert 'public2' in titles
    assert 'assigned_to_client' in titles
    assert 'private_no' not in titles

    # GET individual: allowed for public and assigned, forbidden for private
    rv = client.get(f"/api/tasks/{public['id']}")
    assert rv.status_code == 200
    rv = client.get(f"/api/tasks/{assigned['id']}")
    assert rv.status_code == 200
    rv = client.get(f"/api/tasks/{private['id']}")
    assert rv.status_code == 403


def test_internal_user_can_see_private_task(client, db, create_user, create_project, create_task, login):
    p = create_project(name='V2')
    creator = create_user(email='creator2@example.com', is_internal=True)
    t = create_task(project_id=p['id'], title='private2', is_external_visible=False, via_api=False)

    # sanity check: ensure task exists in DB
    from app.models import Task
    assert Task.query.count() == 1

    # login as internal user to check visibility
    u = create_user(email='int@example.com', is_internal=True)
    login(u)

    rv = client.get(f"/api/tasks?project_id={p['id']}")
    data = rv.get_json()
    assert data['meta']['total'] == 1

    rv = client.get(f"/api/tasks/{t['id']}")
    assert rv.status_code == 200


def test_unauthenticated_user_sees_only_external(client, db, create_project, create_task):
    p = create_project(name='V3')
    # create tasks directly in DB for setup
    t1 = create_task(project_id=p['id'], title='public', is_external_visible=True, via_api=False)
    t2 = create_task(project_id=p['id'], title='private', is_external_visible=False, via_api=False)

    rv = client.get(f"/api/tasks?project_id={p['id']}")
    data = rv.get_json()
    assert data['meta']['total'] == 1
    assert data['items'][0]['is_external_visible'] == True
