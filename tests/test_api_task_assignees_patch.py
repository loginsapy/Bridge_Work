def test_patch_clears_assignees_and_assigned_to(client, db, create_project, create_task, create_user, login):
    # Setup users and task with multiple assignees
    u1 = create_user(email='u1@example.com', is_internal=True)
    u2 = create_user(email='u2@example.com', is_internal=True)
    admin = create_user(email='admin@example.com', is_internal=True)
    from app.models import Role
    # Ensure admin has PMP or Admin role - reuse existing if present
    admin_role = Role.query.filter_by(name='PMP').first()
    if not admin_role:
        admin_role = Role(name='PMP')
        db.session.add(admin_role)
        db.session.commit()
    admin.role = admin_role
    db.session.commit()

    login(admin)
    p = create_project(name='P-patch')
    t = create_task(project_id=p['id'], title='ClearAssignees')

    # Assign via API
    rv = client.patch(f"/api/tasks/{t['id']}", json={'assignees': [u1.id, u2.id], 'assigned_to_id': u1.id})
    assert rv.status_code == 200
    from app.models import Task
    td = Task.query.get(t['id'])
    assert set([u.id for u in td.assignees]) >= set([u1.id, u2.id])
    assert td.assigned_to_id == u1.id

    # Now clear via API: assigned_to_id null and assignees []
    rv2 = client.patch(f"/api/tasks/{t['id']}", json={'assigned_to_id': None, 'assignees': []})
    assert rv2.status_code == 200
    td2 = Task.query.get(t['id'])
    assert td2.assigned_to_id is None
    assert (td2.assignees or []) == []