def test_client_cannot_create_project_ui(client, db, create_user, login):
    from app.models import Project

    client_user = create_user(email='client_no_create@example.com', is_internal=False)
    login(client_user)

    rv = client.post('/projects/new', data={'name': 'BlockedProject'}, follow_redirects=True)
    assert rv.status_code == 200

    p = Project.query.filter_by(name='BlockedProject').first()
    assert p is None


def test_participant_cannot_create_project_ui(client, db, create_user, login):
    from app.models import Project, Role

    # Create participant role and user
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='participant@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    login(participant)
    rv = client.post('/projects/new', data={'name': 'BlockedByParticipant'}, follow_redirects=True)
    assert rv.status_code == 200

    p = Project.query.filter_by(name='BlockedByParticipant').first()
    assert p is None


def test_participant_cannot_create_task_ui(client, db, create_user, create_project, login):
    from app.models import Task, Role

    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='participant_task@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    p = create_project(name='ProjectForTask')

    login(participant)
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'BlockedTask'}, follow_redirects=True)
    assert rv.status_code == 200

    t = Task.query.filter_by(title='BlockedTask').first()
    assert t is None


def test_client_and_participant_cannot_see_new_project_button(client, db, create_user, login):
    # client
    client_user = create_user(email='viewclient@example.com', is_internal=False)
    login(client_user)
    rv = client.get('/projects')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' not in html

    # participant
    from app.models import Role
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='viewparticipant@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    login(participant)
    rv = client.get('/projects')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' not in html


def test_participant_cannot_create_project_api(client, db, create_user, login):
    from app.models import Role

    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='participant_api@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    login(participant)
    rv = client.post('/api/projects', json={'name': 'APIBlocked'})
    assert rv.status_code == 403


def test_participant_cannot_create_task_api(client, db, create_user, create_project, login):
    from app.models import Role

    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='participant_task_api@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    p = create_project(name='APIProject')
    login(participant)
    rv = client.post('/api/tasks', json={'project_id': p['id'], 'title': 'APIBlockedTask'})
    assert rv.status_code == 403
