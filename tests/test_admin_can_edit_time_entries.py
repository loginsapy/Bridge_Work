def test_admin_can_edit_any_time_entry_and_mark_billable(client, db, create_user, create_project, login):
    # Create admin and participant
    admin = create_user(email='adminedit@example.com', is_internal=True)
    participant = create_user(email='partedit2@example.com', is_internal=True)

    # Ensure participant role
    from app.models import Role, Task, TimeEntry, Project, db as _db
    part_role = Role(name='Participante')
    _db.session.add(part_role)
    _db.session.commit()
    participant.role = part_role
    _db.session.commit()

    # Create project and task, assign participant
    login(admin)
    p = create_project(name='P-admin-edit')
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'AdminEditTask', 'assignees': [str(participant.id)], 'submit': 'Create'}, follow_redirects=True)
    assert rv.status_code == 200

    # Find task id
    t = client.get(f"/api/tasks?project_id={p['id']}").get_json()['items'][0]

    # Create time entry as participant
    from app import db as _db
    te = TimeEntry(task_id=t['id'], user_id=participant.id, date=None, hours=1.0, description='Initial')
    _db.session.add(te)
    _db.session.commit()

    # Login as admin and view task detail: should see edit link
    login(admin)
    rv2 = client.get(f"/task/{t['id']}")
    html = rv2.get_data(as_text=True)
    assert f"/time-entry/{te.id}/edit" in html

    # Admin posts edit to change hours and mark as billable
    rv3 = client.post(f"/time-entry/{te.id}/edit", data={
        'date': '2026-01-01',
        'hours': '2.5',
        'description': 'Admin updated',
        'is_billable': 'on'
    }, follow_redirects=True)
    assert rv3.status_code == 200

    # Fetch entry and check changes
    updated = TimeEntry.query.get(te.id)
    assert float(updated.hours) == 2.5
    assert updated.description == 'Admin updated'
    assert updated.is_billable is True
