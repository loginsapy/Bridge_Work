def test_participant_sees_task_preselected_when_clicking_from_task_detail(client, db, create_user, create_project, create_task, login):
    # Create a project and a task with participant as assignee (via many-to-many)
    p = create_project(name='P-preselect')
    participant = create_user(email='parttime@example.com', is_internal=True)
    # Ensure role 'Participante' exists and assign
    from app.models import Role, User, Task
    part_role = Role(name='Participante')
    db.session.add(part_role)
    db.session.commit()
    participant.role = part_role
    db.session.commit()

    # Create admin to create task and add participant as assignee
    admin = create_user(email='admtt@example.com', is_internal=True)
    login(admin)
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'PreselectTask', 'assignees': [str(participant.id)], 'submit': 'Create'}, follow_redirects=True)
    assert rv.status_code == 200

    # Get created task id
    rv2 = client.get(f"/api/tasks?project_id={p['id']}")
    task_list = rv2.get_json()
    assert task_list['items']
    t = task_list['items'][0]

    # Now login as participant and click the 'Registrar' link via direct GET
    login(participant)
    rv3 = client.get(f"/time-entries/new?task_id={t['id']}")
    assert rv3.status_code == 200
    html = rv3.get_data(as_text=True)

    # Ensure the task appears in the select AND is preselected
    assert f'<option value="{t["id"]}"' in html
    assert 'selected' in html.split(f'<option value="{t["id"]}"')[1].split('>')[0]
