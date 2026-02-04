def test_tasks_page_has_all_status_filters_and_wbs_and_multi_assignees(client, db, create_project, create_task, create_user, login):
    # Create users and assign them
    u1 = create_user(email='u1ui@example.com', is_internal=True, first_name='U1')
    u2 = create_user(email='u2ui@example.com', is_internal=True, first_name='U2')
    admin = create_user(email='adminui@example.com', is_internal=True)

    # Ensure admin role exists
    from app.models import Role
    r = Role.query.filter_by(name='PMP').first()
    if not r:
        r = Role(name='PMP')
        db.session.add(r)
        db.session.commit()
    admin.role = r
    db.session.commit()

    login(admin)
    p = create_project(name='P-ui-format')

    # Create a task with multiple assignees and a WBS number
    t = create_task(project_id=p['id'], title='UI Multi', via_api=False)
    from app.models import Task, User
    td = Task.query.get(t['id'])
    td.assignees = [User.query.get(u1.id), User.query.get(u2.id)]
    td.wbs_number = '1.3'
    db.session.commit()

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.data.decode()
    # Check WBS appears
    assert '1.3' in html
    # Check both assignee initials appear (U1, U2)
    assert 'U1' in html
    assert 'U2' in html
    # Check the status filter buttons include TODO and COMPLETED
    assert 'data-status="COMPLETED"' in html
    assert 'data-status="DONE"' in html

    # The tasks page should include the project-style header and completion percentage
    assert 'project-board-header' in html
    assert '0% completado' in html