def test_assign_adds_user_does_not_remove_existing(client, db, create_project, create_task, create_user, login):
    # Create project and two users
    p = create_project(name='Assign Additive')
    u1 = create_user(first_name='Ana', last_name='García', email='ana2@example.com')
    u2 = create_user(first_name='Pedro', last_name='Martín', email='pedro@example.com')

    # Create a task and set initial assignees to [u1]
    rv = client.post(f"/project/{p.id}/tasks/new", data={
        'title': 'Task to add assignees',
        'assignees': [str(u1.id)],
        'submit': 'Create'
    }, follow_redirects=True)
    assert rv.status_code == 200

    # Get the task via API to find its id
    api_list = client.get(f"/api/tasks?project_id={p.id}")
    assert api_list.status_code == 200
    data = api_list.get_json()
    assert data['items']
    t = data['items'][0]

    # Simulate the additive assign behavior performed by the frontend: fetch, merge and patch
    get_t = client.get(f"/api/tasks/{t['id']}")
    assert get_t.status_code == 200
    task_data = get_t.get_json()
    current_assignees = task_data.get('assignees', [])
    assert u1.id in current_assignees

    merged = list(set(current_assignees + [u2.id]))
    rv2 = client.patch(f"/api/tasks/{t['id']}", json={'assignees': merged})
    assert rv2.status_code == 200

    # Confirm both users are now assignees
    get_after = client.get(f"/api/tasks/{t['id']}")
    assert get_after.status_code == 200
    after_data = get_after.get_json()
    assert set(after_data.get('assignees', [])) == set(merged)
