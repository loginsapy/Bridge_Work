def test_create_project_missing_name_returns_400(client, db, create_user, login):
    # must be internal to create
    admin = create_user(email='admin@example.com', is_internal=True)
    login(admin)

    rv = client.post('/api/projects', json={})
    assert rv.status_code == 400
    data = rv.get_json()
    assert 'errors' in data


def test_create_time_entry_invalid_date_returns_400(client, db, create_user, create_project, create_task):
    # create project and task & user via helpers
    project = create_project(name='P3')
    task = create_task(project_id=project['id'], title='T3')
    user = create_user(email='bad@example.com')

    rv = client.post('/api/time_entries', json={"task_id": task['id'], "user_id": user.id, "date": "not-a-date", "hours": 1})
    assert rv.status_code == 400
    data = rv.get_json()
    assert 'errors' in data
    assert 'date' in data['errors']


def test_create_time_entry_negative_hours_returns_400(client, db, create_project, create_task):
    project = create_project(name='P4')
    task = create_task(project_id=project['id'], title='T4')
    from app.models import User
    user = User(email='neg@example.com')
    from app import db
    db.session.add(user)
    db.session.commit()

    rv = client.post('/api/time_entries', json={"task_id": task['id'], "user_id": user.id, "date": "2025-12-22", "hours": -5})
    assert rv.status_code == 400
    data = rv.get_json()
    assert 'errors' in data
    assert 'hours' in data['errors']
