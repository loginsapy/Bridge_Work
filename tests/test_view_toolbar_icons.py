def test_kanban_toolbar_icons_match_board(client, db, create_user, create_project, create_task, login):
    admin = create_user(email='iconadmin@example.com', is_internal=True)
    login(admin)
    p = create_project(name='P-icons')

    # Ensure at least one task exists
    client.post('/task', data={'project_id': p['id'], 'title': 'IconTask', 'submit': 'Create'}, follow_redirects=True)

    rv = client.get(f"/project/{p['id']}/kanban")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Buttons should have toolbar-btn and include visually-hidden spans for accessibility
    assert 'class="toolbar-btn"' in html
    assert '<span class="visually-hidden">Board</span>' in html
    assert '<span class="visually-hidden">Kanban</span>' in html
    assert '<span class="visually-hidden">Gantt</span>' in html
    # Hover/active behavior class should match board (we check presence of shared CSS rule)
    css_text = open('app/static/css/board-shared.css', encoding='utf-8').read()
    assert 'background: var(--monday-blue)' in css_text
    assert 'color: white' in css_text

    # Board page should match too (icon-only buttons)
    rvb = client.get(f"/project/{p['id']}")
    assert rvb.status_code == 200
    h2 = rvb.get_data(as_text=True)
    assert '<span class="visually-hidden">Board</span>' in h2
    assert '<span class="visually-hidden">Kanban</span>' in h2
    assert '<span class="visually-hidden">Gantt</span>' in h2


def test_gantt_toolbar_icons_match_board(client, db, create_user, create_project, create_task, login):
    admin = create_user(email='ganttadm@example.com', is_internal=True)
    login(admin)
    p = create_project(name='P-gantt-icons')
    client.post('/task', data={'project_id': p['id'], 'title': 'GanttTask', 'submit': 'Create'}, follow_redirects=True)

    rv = client.get(f"/project/{p['id']}/gantt")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    assert 'class="toolbar-btn"' in html
    assert '<span class="visually-hidden">Board</span>' in html
    assert '<span class="visually-hidden">Kanban</span>' in html
    assert '<span class="visually-hidden">Gantt</span>' in html