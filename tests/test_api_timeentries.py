from app.models import Project, Task, TimeEntry


def test_create_time_entry_requires_fields(client, db):
    rv = client.post('/api/time_entries', json={})
    assert rv.status_code == 400


def test_create_and_get_time_entry(client, db, create_user, create_project, create_task):
    # create project and task via helpers
    project = create_project(name='P2')
    task = create_task(project_id=project['id'], title='T2')

    # create a user via factory helper
    user = create_user(email='u@example.com')

    rv = client.post('/api/time_entries', json={"task_id": task['id'], "user_id": user.id, "date": "2025-12-22", "hours": 3})
    assert rv.status_code == 201
    te = rv.get_json()
    assert te['hours'] == 3.0 or te['hours'] == 3

    rv = client.get(f"/api/time_entries/{te['id']}")
    assert rv.status_code == 200
    t2 = rv.get_json()
    assert t2['id'] == te['id']
