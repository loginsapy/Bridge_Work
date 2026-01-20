def test_dashboard_shows_client_icon_in_kanban_and_recent_projects(client, db, create_user, create_project, login):
    admin = create_user(email='dashadm@example.com', is_internal=True)
    client_user = create_user(email='dashclient@example.com', is_internal=False, first_name='ClienteD')
    login(admin)
    p = create_project(name='P-dash-client')

    from app.models import Project, db as _db
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    rv = client.get('/')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Kanban card should show client-icon and tooltip text
    assert 'class="client-icon"' in html
    assert 'ClienteD (Cliente Externo)' in html or 'dashclient@example.com (Cliente Externo)' in html

    # Recent projects table should show the client icon + name
    assert 'ClienteD' in html or 'dashclient@example.com' in html


def test_projects_list_and_grid_show_client_icon(client, db, create_user, create_project, login):
    admin = create_user(email='projadm@example.com', is_internal=True)
    client_user = create_user(email='projclient@example.com', is_internal=False, first_name='ClienteP')
    login(admin)
    p = create_project(name='P-proj-client')

    from app.models import Project, db as _db
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    rv = client.get('/projects')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Table and grid views should include client-icon and tooltip text
    assert 'class="client-icon"' in html
    assert 'ClienteP (Cliente Externo)' in html or 'projclient@example.com (Cliente Externo)' in html