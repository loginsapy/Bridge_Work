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


def test_time_entry_blocked_by_incomplete_predecessor(client, db, create_user, create_project, create_task):
    """Test that time entries cannot be created for tasks with incomplete predecessors."""
    project = create_project(name='P-time-block')
    
    # Create predecessor task (incomplete)
    t1 = create_task(project_id=project['id'], title='Predecessor Task', status='BACKLOG')
    # Create dependent task with t1 as predecessor
    t2 = create_task(project_id=project['id'], title='Dependent Task', status='BACKLOG')
    
    # Set t1 as predecessor of t2
    task1 = db.session.get(Task, t1['id'])
    task2 = db.session.get(Task, t2['id'])
    task2.predecessors.append(task1)
    db.session.commit()
    
    user = create_user(email='time_block@example.com')
    
    # Try to create time entry for t2 - should fail
    rv = client.post('/api/time_entries', json={
        "task_id": t2['id'], 
        "user_id": user.id, 
        "date": "2025-12-22", 
        "hours": 2
    })
    assert rv.status_code == 400
    data = rv.get_json()
    assert 'predecesoras incompletas' in data.get('error', '').lower() or 'blocked_by' in data
    
    # Complete the predecessor
    task1.status = 'COMPLETED'
    db.session.commit()
    
    # Now time entry should work
    rv = client.post('/api/time_entries', json={
        "task_id": t2['id'], 
        "user_id": user.id, 
        "date": "2025-12-22", 
        "hours": 2
    })
    assert rv.status_code == 201
