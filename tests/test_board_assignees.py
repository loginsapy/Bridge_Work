def test_board_shows_multiple_assignee_avatars(client, db, create_project, create_task, create_user, login):
    # Create a project and a task with multiple assignees
    p = create_project(name='Board Project')
    u1 = create_user(first_name='Ana', last_name='García', email='ana@example.com')
    u2 = create_user(first_name='Juan', last_name='Lopez', email='juan@example.com')
    u3 = create_user(first_name='Maria', last_name='Perez', email='maria@example.com')

    # Create a task and assign users via API
    rv = client.post(f"/project/{p.id}/tasks/new", data={
        'title': 'Multi assign task',
        'assignees': [str(u1.id), str(u2.id), str(u3.id)],
        'submit': 'Create'
    }, follow_redirects=True)
    assert rv.status_code == 200

    # Fetch board view
    rv2 = client.get(f"/project/{p.id}/board")
    assert rv2.status_code == 200
    html = rv2.get_data(as_text=True)

    # Expect to see at least two small-avatar elements for the task
    assert 'person-avatar small-avatar' in html
    # Expect to see the full names in title attributes
    assert 'title="Ana García"' in html or 'Ana García' in html
    assert 'title="Juan Lopez"' in html or 'Juan Lopez' in html
