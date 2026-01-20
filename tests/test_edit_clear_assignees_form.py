def test_edit_clear_assignees_via_form(client, db, create_user, login, create_project, create_task):
    # Setup: create users and assign them to a task
    u1 = create_user(email='e1@example.com', is_internal=True)
    u2 = create_user(email='e2@example.com', is_internal=True)
    u3 = create_user(email='e3@example.com', is_internal=True)

    admin = create_user(email='admin2@example.com', is_internal=True)
    from app.models import Role
    admin_role = Role.query.filter_by(name='PMP').first()
    if not admin_role:
        admin_role = Role(name='PMP')
        db.session.add(admin_role)
        db.session.commit()
    admin.role = admin_role
    db.session.commit()

    login(admin)
    p = create_project(name='P-edit-clear')
    t = create_task(project_id=p['id'], title='ClearViaForm')

    # Assign multiple assignees via API first
    rv = client.patch(f"/api/tasks/{t['id']}", json={'assignees': [u1.id, u2.id, u3.id], 'assigned_to_id': u1.id})
    assert rv.status_code == 200

    # Now submit edit form with no assignees (simulate clearing all)
    from werkzeug.datastructures import MultiDict
    form = MultiDict([
        ('title', 'ClearViaForm'),
        # no 'assignees' entries -> should clear
    ])

    rv2 = client.post(f"/task/{t['id']}/edit", data=form, follow_redirects=True, content_type='multipart/form-data')
    assert rv2.status_code == 200
    from app.models import Task
    td = Task.query.get(t['id'])
    assert td.assigned_to_id is None
    assert (td.assignees or []) == []