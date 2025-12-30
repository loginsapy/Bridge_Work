from app.models import Project, Task


def test_create_task_requires_project_and_title(client, db, create_user, login):
    # missing fields (must be internal to create)
    admin = create_user(email='admin@example.com', is_internal=True)
    login(admin)
    rv = client.post('/api/tasks', json={})
    assert rv.status_code == 400


def test_create_and_get_task(client, db, create_user, login):
    # create a project first (via API) as internal
    admin = create_user(email='admin2@example.com', is_internal=True)
    login(admin)
    rv = client.post('/api/projects', json={"name": "P1"})
    project = rv.get_json()

    rv = client.post('/api/tasks', json={"project_id": project['id'], "title": "Task 1"})
    assert rv.status_code == 201
    task = rv.get_json()
    assert task['title'] == 'Task 1'

    rv = client.get(f"/api/tasks/{task['id']}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['id'] == task['id']
