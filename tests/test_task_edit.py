def test_edit_task_block_completion_when_children_incomplete(client, db, create_project, create_task, create_user, login):
    u = create_user(email='edit_block@example.com', is_internal=True)
    login(u)
    p = create_project('P-edit')
    parent = create_task(project_id=p['id'], title='ParentEdit')
    child = create_task(project_id=p['id'], title='ChildEdit', parent_task_id=parent['id'])

    from app.models import Task
    parent_obj = Task.query.get(parent['id'])

    # Attempt to edit parent and set status to COMPLETED
    rv = client.post(f"/task/{parent_obj.id}/edit", data={'status': 'COMPLETED'}, follow_redirects=True)
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)
    assert 'No se puede completar la tarea mientras existan subtareas incompletas' in data
    # Ensure status didn't change
    parent_obj = Task.query.get(parent['id'])
    assert parent_obj.status != 'COMPLETED'


def test_client_accept_marks_completed(client, db, create_project, create_task, create_user, login):
    # Setup: create a client user and project
    client_user = create_user(email='client@example.com', is_internal=False)
    p = create_project(name='P-client', client_id=client_user.id)
    t = create_task(project_id=p['id'], title='ClientTask')

    # Login as client
    login(client_user)

    # Accept task
    rv = client.post(f"/task/{t['id']}/client_accept", follow_redirects=True)
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)
    assert 'Tarea aceptada y marcada como completada.' in data

    from app.models import Task
    t_obj = Task.query.get(t['id'])
    assert t_obj.status == 'COMPLETED'
    assert t_obj.approval_status == 'APPROVED'
    assert t_obj.approved_by_id == client_user.id
