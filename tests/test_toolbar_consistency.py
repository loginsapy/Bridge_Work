def test_toolbar_button_styles_are_unified(client, db, create_user, create_project, create_task, login):
    admin = create_user(email='styleadm@example.com', is_internal=True)
    login(admin)
    p = create_project(name='P-style')

    # Fetch CSS and templates
    css_text = open('app/static/css/board-shared.css').read()
    # Active toolbar style should use the Gantt look: blue background and white icon
    assert 'background: var(--monday-blue)' in css_text
    assert 'color: white' in css_text

    # Ensure no template defines overriding toolbar-btn rules
    board_text = open('app/templates/board.html', encoding='utf-8').read()
    kanban_text = open('app/templates/kanban.html', encoding='utf-8').read()
    gantt_text = open('app/templates/gantt.html', encoding='utf-8').read()

    # Templates should not contain full toolbar CSS blocks (no background/border overrides)
    assert '.toolbar-btn:hover' not in board_text
    assert '.toolbar-btn.active' not in board_text
    assert '.toolbar-btn:hover' not in kanban_text
    assert '.toolbar-btn.active' not in kanban_text
    # Gantt keeps localized toolbar rules for spacing and sizing; that's intentional

    # Render pages to ensure visually-hidden spans exist
    rv1 = client.get(f"/project/{p['id']}")
    rv2 = client.get(f"/project/{p['id']}/kanban")
    rv3 = client.get(f"/project/{p['id']}/gantt")
    assert rv1.status_code == 200 and rv2.status_code == 200 and rv3.status_code == 200
    h1 = rv1.get_data(as_text=True)
    h2 = rv2.get_data(as_text=True)
    h3 = rv3.get_data(as_text=True)
    assert '<span class="visually-hidden">Board</span>' in h1
    assert '<span class="visually-hidden">Kanban</span>' in h2
    assert '<span class="visually-hidden">Gantt</span>' in h3
