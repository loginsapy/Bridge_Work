def test_project_detail_shows_client_assignment(client, db, create_project, create_user, login):
    admin = create_user(email='show_admin@example.com', is_internal=True)
    client_user = create_user(email='show_client@example.com', is_internal=False, first_name='ClienteX')
    login(admin)
    p = create_project(name='P-show-client')

    from app.models import Project, db as _db, Task
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # create a task assigned to client
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'T-show', 'assigned_client_id': str(client_user.id)}, follow_redirects=True)
    assert rv.status_code == 200
    # Explicitly load the project page (table view) and assert there the assigned client is shown
    rv2 = client.get(f"/project/{p['id']}")
    assert rv2.status_code == 200
    data = rv2.get_data(as_text=True)
    # Ensure client's name/email appears in task list
    assert 'ClienteX' in data or 'show_client@example.com' in data
    # Ensure we do not show the literal 'Cliente:' label and we show the client icon with tooltip
    assert 'Cliente:' not in data
    assert 'class="client-icon"' in data
    assert 'ClienteX (Cliente Externo)' in data or 'show_client@example.com (Cliente Externo)' in data
