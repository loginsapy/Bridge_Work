def test_client_cannot_see_add_task_buttons_on_kanban(client, db, create_user, create_project, create_task, login):
    client_user = create_user(email='kanbanclient@example.com', is_internal=False)
    p = create_project(name='KanbanP')
    login(client_user)

    rv = client.get(f"/project/{p['id']}/kanban")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Añadir tarea' not in html


def test_client_cannot_see_new_from_project_on_tasks_page(client, db, create_user, login):
    client_user = create_user(email='tasksclient@example.com', is_internal=False)
    login(client_user)

    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Nueva desde Proyecto' not in html


def test_participant_cannot_see_new_from_project_on_tasks_page(client, db, create_user, login):
    from app.models import Role
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='tasksparticipant@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    login(participant)
    rv = client.get('/tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Nueva desde Proyecto' not in html

def test_participant_cannot_see_add_task_buttons_on_kanban(client, db, create_user, create_project, create_task, login):
    from app.models import Role
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='kanbanparticipant@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    p = create_project(name='KanbanP2')
    login(participant)

    rv = client.get(f"/project/{p['id']}/kanban")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Añadir tarea' not in html