def test_client_cannot_see_edit_button_on_time_entries(client, db, create_user, create_project, login):
    admin = create_user(email='admtec@example.com', is_internal=True)
    client_user = create_user(email='cli_te@example.com', is_internal=False)
    login(admin)
    p = create_project(name='P-client-edit')

    from app.models import Project, db as _db, Task, TimeEntry
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # create a task visible to client
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'T-client-visible', 'is_external_visible': 'y'}, follow_redirects=True)
    assert rv.status_code == 200

    # find task id
    tasks = client.get(f"/api/tasks?project_id={p['id']}").get_json()['items']
    t = tasks[0]

    # create time entry by admin
    te = TimeEntry(task_id=t['id'], user_id=admin.id, date=None, hours=2, description='Work')
    _db.session.add(te)
    _db.session.commit()

    # login as client and view task detail
    login(client_user)
    rv2 = client.get(f"/task/{t['id']}")
    assert rv2.status_code == 200
    html = rv2.get_data(as_text=True)

    # client should not see edit link for this time entry
    assert f"/time-entry/{te.id}/edit" not in html


def test_participant_can_see_edit_for_own_time_entry(client, db, create_user, create_project, login):
    participant = create_user(email='partedit@example.com', is_internal=True)
    # assign participant role
    from app.models import Role, db as _db, Task, TimeEntry
    part_role = Role(name='Participante')
    _db.session.add(part_role)
    _db.session.commit()
    participant.role = part_role
    _db.session.commit()

    login(participant)
    p = create_project(name='P-part-edit')

    # create task and create time entry as participant
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'T-part-edit', 'assignees': [str(participant.id)], 'submit': 'Create'}, follow_redirects=True)
    assert rv.status_code == 200

    tasks = client.get(f"/api/tasks?project_id={p['id']}").get_json()['items']
    t = tasks[0]

    from app import db as _db
    te = TimeEntry(task_id=t['id'], user_id=participant.id, date=None, hours=1.5, description='Dev work')
    _db.session.add(te)
    _db.session.commit()

    rv2 = client.get(f"/task/{t['id']}")
    assert rv2.status_code == 200
    html = rv2.get_data(as_text=True)

    # Participant should see edit link for own entry
    assert f"/time-entry/{te.id}/edit" in html
