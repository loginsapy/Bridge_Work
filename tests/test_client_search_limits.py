def test_client_search_sees_only_their_projects_and_tasks(client, db, create_user, login, create_project, create_task):
    from app.models import project_clients

    # Create client user (external)
    client_user = create_user(email='client_search@example.com', is_internal=False)

    # Create a project linked to the client
    p1 = create_project(name='ClientProject')
    # link client to project via association table
    from app import db as _db
    _db.session.execute(project_clients.insert().values(project_id=p1['id'], user_id=client_user.id))
    _db.session.commit()

    # Create a visible task in that project
    t1 = create_task(project_id=p1['id'], title='ClientTask', is_external_visible=True, assigned_to_id=None)

    # Create another project not linked
    p2 = create_project(name='OtherProject')
    t2 = create_task(project_id=p2['id'], title='OtherTask', is_external_visible=True, assigned_to_id=None)

    login(client_user)
    rv = client.get('/search?q=Client')
    assert rv.status_code == 200
    data = rv.get_json()
    # Ensure client's linked project/task appear
    assert any('ClientProject' in p['name'] for p in data.get('projects', []))
    assert any('ClientTask' in t['title'] for t in data.get('tasks', []))

    # Searching for Other should not return non-linked project
    rv2 = client.get('/search?q=Other')
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    assert not any('OtherProject' in p['name'] for p in data2.get('projects', []))
    assert not any('OtherTask' in t['title'] for t in data2.get('tasks', []))
