import pytest
from app.models import Task, Project, db


def test_complete_child_allowed_unless_predecessor_blocks(client, create_user, create_project, create_task, login):
    u = create_user(email='test_user2@example.com', is_internal=True)
    login(u)
    p = create_project('Status-Rules')
    parent = create_task(project_id=p['id'], title='ParentSR')
    child = create_task(project_id=p['id'], title='ChildSR', parent_task_id=parent['id'])

    # Completing child should be allowed even if parent is incomplete
    rv = client.patch(f"/api/tasks/{child['id']}", json={'status': 'DONE'})
    assert rv.status_code == 200

    # If child has explicit predecessor that is incomplete, completing child is blocked
    # Create another task as predecessor
    pred = create_task(project_id=p['id'], title='PredSR')
    # add predecessor relationship
    pred_obj = Task.query.get(pred['id'])
    child_obj = Task.query.get(child['id'])
    child_obj.predecessors = [pred_obj]
    db.session.commit()

    rv = client.patch(f"/api/tasks/{child['id']}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_predecessors' in j


def test_validate_predecessor_ids_blocks_cross_graph_cycle(create_project, create_task):
    p = create_project('CycleTest')
    a = create_task(project_id=p['id'], title='A')
    b = create_task(project_id=p['id'], title='B', parent_task_id=a['id'])

    a_obj = Task.query.get(a['id'])
    b_obj = Task.query.get(b['id'])

    # Trying to add B as predecessor of A should be rejected (would create hierarchical cycle)
    with pytest.raises(ValueError):
        a_obj.validate_predecessor_ids([b_obj.id])
