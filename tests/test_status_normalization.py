def test_status_normalization_on_api_patch(client, db, create_user, create_project, create_task, login):
    u = create_user(email='norm@example.com', is_internal=True)
    login(u)

    p = create_project(name='Norm')
    t = create_task(project_id=p['id'], title='NormTask')

    # Patch status to legacy value 'DONE' via API - should be normalized to 'COMPLETED'
    rv = client.patch(f"/api/tasks/{t['id']}", json={'status': 'DONE'})
    assert rv.status_code == 200

    from app.models import Task
    t_obj = Task.query.get(t['id'])
    assert t_obj.status == 'COMPLETED'
