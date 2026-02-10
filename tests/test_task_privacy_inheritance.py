def test_privacy_propagates_to_children(client, db, create_user, create_project, login):
    # Setup users
    editor = create_user('editor2@example.com', first_name='Editor2', is_internal=True)
    client_user = create_user('cust@example.com', first_name='Client', is_internal=False)

    # Create project and assign client
    p = create_project(name='PrivProj')
    from app.models import Project, Task
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    proj.client_id = client_user.id
    from app import db as _db
    _db.session.commit()

    # Create parent and child tasks
    parent = Task(project_id=proj.id, title='Parent Private Test')
    _db.session.add(parent)
    _db.session.commit()

    child = Task(project_id=proj.id, title='Child of Parent', parent_task_id=parent.id)
    grandchild = Task(project_id=proj.id, title='Grandchild Task', parent_task_id=child.id)
    _db.session.add_all([child, grandchild])
    _db.session.commit()

    # Login as editor (PMP role assigned by fixture)
    login(editor)

    # Mark parent as internal-only via edit POST
    rv = client.post(f'/task/{parent.id}/edit', data={'title': parent.title, 'is_internal_only': 'on'}, follow_redirects=True)
    assert rv.status_code in (200, 302)

    # Now simulate client view of project detail; client should NOT see child tasks
    login(client_user)
    rv2 = client.get(f'/project/{proj.id}')
    assert rv2.status_code == 200
    html = rv2.get_data(as_text=True)

    assert 'Parent Private Test' not in html
    assert 'Child of Parent' not in html
    assert 'Grandchild Task' not in html

    # As a PMP/Admin the tasks should still be visible
    login(editor)
    rv3 = client.get(f'/project/{proj.id}')
    html_admin = rv3.get_data(as_text=True)
    assert 'Parent Private Test' in html_admin
    assert 'Child of Parent' in html_admin
    assert 'Grandchild Task' in html_admin
