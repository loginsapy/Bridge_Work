def test_project_edit_shows_all_internal_members(client, db, create_user, create_project, login):
    # Setup: create editor and internal users
    editor = create_user('editor@example.com', first_name='Editor', is_internal=True)
    alice = create_user('alice@example.com', first_name='Alice', is_internal=True)
    bob = create_user('bob@example.com', first_name='Bob', is_internal=True)

    # Create a project
    p = create_project(name='TestProject')
    project_id = p['id']

    # Login as editor (PMP role assigned by fixture)
    login(editor)

    # GET edit page
    rv = client.get(f'/project/{project_id}/edit')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Both internal users should appear in the members multi-select
    assert 'Alice' in html
    assert 'Bob' in html
