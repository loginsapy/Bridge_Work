import json
from app.models import Project


def test_create_and_get_project(client, db, create_user, login):
    # need internal user to create via API
    admin = create_user(email='admin@example.com', is_internal=True)
    login(admin)

    payload = {"name": "Test Project", "status": "ACTIVE"}
    rv = client.post('/api/projects', json=payload)
    assert rv.status_code == 201
    data = rv.get_json()
    assert data['name'] == 'Test Project'

    project_id = data['id']

    # Retrieve project
    rv = client.get(f'/api/projects/{project_id}')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['id'] == project_id
    assert data['status'] == 'ACTIVE'


def test_list_projects_empty(client, db):
    rv = client.get('/api/projects')
    assert rv.status_code == 200
    data = rv.get_json()
    # Paginated response: { items: [], meta: {...} }
    assert isinstance(data, dict)
    assert data['items'] == []
    assert data['meta']['total'] == 0
