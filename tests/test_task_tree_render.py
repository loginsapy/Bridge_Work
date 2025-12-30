def test_tasks_render_as_tree(client, db, create_project, create_task, create_user, login):
    # Create internal user and login
    u = create_user(email='u_tree@example.com', is_internal=True)
    login(u)

    p = create_project(name='P-tree')
    t1 = create_task(project_id=p['id'], title='Parent Task')
    t2 = create_task(project_id=p['id'], title='Child Task')

    from app.models import Task, db as _db
    t1_obj = Task.query.get(t1['id'])
    t2_obj = Task.query.get(t2['id'])

    # Set t1 as predecessor of t2 (Parent -> Child)
    t2_obj.predecessors = [t1_obj]
    _db.session.commit()

    rv = client.get(f"/project/{p['id']}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    # Parent should appear before child and child-row class should exist
    assert html.index('Parent Task') < html.index('Child Task')
    assert 'child-row' in html
    # Parent should have a toggle icon (chevron) and child should have data-parent-id
    assert 'toggle-icon-' + str(t1_obj.id) in html
    assert f'data-parent-id="{t1_obj.id}"' in html
    # Connector span present for child
    assert 'class="connector"' in html
    # Ensure expand/collapse JS functions are present and defined in template to avoid runtime errors
    assert 'window.toggleNode' in html
    assert 'window.hideDescendants' in html
