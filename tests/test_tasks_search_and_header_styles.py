def test_tasks_search_includes_assignee_and_header_button_style(client, db, create_user, login):
    admin = create_user(email='searchui@example.com', is_internal=True)
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()
    admin.role = r
    db.session.commit()

    login(admin)
    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.data.decode()
    # Search script should include assignee checks and attribute-based search
    assert 'assignee.includes(searchTerm)' in html
    assert "assignee-cell [title]" in html or "assignee-cell [aria-label]" in html
    # The header button override style should exist in the page
    assert '.tasks-page-header .monday-btn-primary' in html
