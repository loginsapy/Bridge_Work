def test_time_page_has_toolbar_and_search(client, db, create_user, login):
    u = create_user(email='u-tui@example.com', is_internal=True)
    login(u)
    rv = client.get('/time')
    assert rv.status_code == 200
    html = rv.data.decode()
    # Toolbar card and search input should be present
    assert 'tasks-toolbar' in html
    assert 'id="timeSearch"' in html
