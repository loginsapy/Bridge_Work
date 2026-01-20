def test_project_reports_pagination(client, db, create_user, create_project, create_task, login):
    u = create_user(email='pag@example.com', is_internal=True)
    login(u)

    p = create_project(name='PagP')
    # create 25 tasks with distinct titles
    for i in range(1, 26):
        create_task(project_id=p['id'], title=f'Task {i}')

    # Request page 2 (items 11-20)
    rv = client.get(f"/reports?project_id={p['id']}&page=2")
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)

    # Should contain tasks 11 and 20, and not contain Task 1 (which should be on page 1)
    assert 'Task 11' in data
    assert 'Task 20' in data
    assert 'Task 1' not in data
