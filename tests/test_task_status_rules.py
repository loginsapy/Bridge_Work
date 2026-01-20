import pytest
from app.models import Task, Project, db


def test_complete_child_allowed_with_predecessor_parent(client, create_user, create_project, create_task, login):
    """Test that children (successors in tree) CAN be completed even if predecessors (parents) are incomplete.
    
    In our tree model: predecessor = visual parent, successor = visual child.
    Children must close FIRST, then parents can close.
    """
    u = create_user(email='test_user2@example.com', is_internal=True)
    login(u)
    p = create_project('Status-Rules')
    parent = create_task(project_id=p['id'], title='ParentSR')
    child = create_task(project_id=p['id'], title='ChildSR', parent_task_id=parent['id'])

    # Completing child should be allowed even if parent is incomplete
    rv = client.patch(f"/api/tasks/{child['id']}", json={'status': 'COMPLETED'})
    assert rv.status_code == 200

    # If child has explicit predecessor, child can STILL be completed (predecessor doesn't block)
    pred = create_task(project_id=p['id'], title='PredSR')
    pred_obj = Task.query.get(pred['id'])
    child_obj = Task.query.get(child['id'])
    child_obj.predecessors = [pred_obj]
    db.session.commit()

    # Child can be completed - predecessors don't block in tree model
    rv = client.patch(f"/api/tasks/{child['id']}", json={'status': 'COMPLETED'})
    assert rv.status_code == 200, f"Child should complete: {rv.get_json()}"



def test_validate_predecessor_ids_blocks_cross_graph_cycle(create_project, create_task):
    p = create_project('CycleTest')
    a = create_task(project_id=p['id'], title='A')
    b = create_task(project_id=p['id'], title='B', parent_task_id=a['id'])

    a_obj = Task.query.get(a['id'])
    b_obj = Task.query.get(b['id'])

    # Trying to add B as predecessor of A should be rejected (would create hierarchical cycle)
    with pytest.raises(ValueError):
        a_obj.validate_predecessor_ids([b_obj.id])


def test_predecessor_dependency_not_considered_ancestor(create_project, create_task):
    p = create_project('PreDepTest')
    parent = create_task(project_id=p['id'], title='Parent')
    child = create_task(project_id=p['id'], title='Child', parent_task_id=parent['id'])
    pred = create_task(project_id=p['id'], title='Pred')

    child_obj = Task.query.get(child['id'])
    pred_obj = Task.query.get(pred['id'])

    # Link pred as predecessor of child (dependency edge only)
    child_obj.predecessors = [pred_obj]
    db.session.commit()

    # validate_predecessor_ids should accept pred as a valid predecessor (not an ancestor)
    assert child_obj.validate_predecessor_ids([pred_obj.id]) is True
