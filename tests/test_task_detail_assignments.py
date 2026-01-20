def test_task_detail_shows_multiple_assignees_and_client(client, db, create_user, create_project, login):
    # Setup users
    u1 = create_user(email='detail_a@example.com', is_internal=True, first_name='DetailA')
    u2 = create_user(email='detail_b@example.com', is_internal=True, first_name='DetailB')
    client_user = create_user(email='clientx@example.com', is_internal=False, first_name='ClientX')

    # Login as u1
    login(u1)

    p = create_project(name='DetailP', via_api=False)

    # Create task via form with multiple assignees and assigned_client_id
    rv = client.post('/task', data={
        'project_id': p['id'],
        'title': 'DetailMulti',
        'assignees': [str(u1.id), str(u2.id)],
        'assigned_client_id': str(client_user.id)
    }, follow_redirects=True)
    assert rv.status_code == 200

    # Find created task id via API
    rv2 = client.get(f"/api/tasks?project_id={p['id']}")
    items = rv2.get_json().get('items', [])
    found = None
    for t in items:
        if t.get('title') == 'DetailMulti':
            found = t
            break
    assert found is not None

    # Fetch task detail HTML
    rv3 = client.get(f"/task/{found['id']}")
    html = rv3.get_data(as_text=True)

    assert 'DetailA' in html
    assert 'DetailB' in html
    assert 'ClientX' in html
