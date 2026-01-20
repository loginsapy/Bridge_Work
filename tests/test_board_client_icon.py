def test_board_shows_client_building_icon_and_tooltip(client, db, create_project, create_user, login):
    admin = create_user(email='admincb@example.com', is_internal=True)
    client_user = create_user(email='clientcb@example.com', is_internal=False, first_name='ClienteX')
    login(admin)
    p = create_project(name='P-client-icon')

    from app.models import Project, db as _db
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # create a task assigned to client
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'T-client-icon', 'assigned_client_id': str(client_user.id)}, follow_redirects=True)
    assert rv.status_code == 200

    # Board view should show a building icon with title 'ClienteX (Cliente Externo)'
    rv2 = client.get(f"/project/{p['id']}/board")
    assert rv2.status_code == 200
    html = rv2.get_data(as_text=True)

    assert 'class="client-icon"' in html
    assert 'fa-building' in html
    assert 'ClienteX (Cliente Externo)' in html or 'clientcb@example.com (Cliente Externo)' in html
    # Ensure we do not show the literal 'Cliente:' label in the board view
    assert 'Cliente:' not in html
