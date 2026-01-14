import pytest
from app.models import Task, db


def test_parent_blocked_until_child_completed(client, create_user, create_project, create_task, login):
    """Test that parent task cannot be completed until child (hierarchical) is completed."""
    # Arrange
    u = create_user(email='parent_admin@example.com', is_internal=True)
    login(u)
    p = create_project('ParentBlock')
    parent = create_task(project_id=p['id'], title='Parent')
    child = create_task(project_id=p['id'], title='Child', parent_task_id=parent['id'])

    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # Act: try to complete parent via API
    rv = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_children' in j

    # Now complete child and try again
    rv2 = client.patch(f"/api/tasks/{child_obj.id}", json={'status': 'DONE'})
    assert rv2.status_code == 200

    rv3 = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'DONE'})
    assert rv3.status_code == 200
    j3 = rv3.get_json()
    assert 'incomplete_children' not in j3


def test_predecessor_blocked_until_successor_completed(client, create_user, create_project, create_task, login):
    """Test that a predecessor (tree parent) cannot be completed until its successor (tree child) is completed.
    
    In our tree model:
    - predecessor = visual parent in tree
    - successor = visual child in tree
    - Children must be closed BEFORE parents
    """
    u = create_user(email='pred_admin@example.com', is_internal=True)
    login(u)
    p = create_project('PredBlock')
    
    # Create predecessor (parent in tree) and successor (child in tree)
    pred = create_task(project_id=p['id'], title='Predecessor-Parent')
    succ = create_task(project_id=p['id'], title='Successor-Child')
    
    # Link them: successor has pred as predecessor
    from app.models import db as _db
    pred_obj = Task.query.get(pred['id'])
    succ_obj = Task.query.get(succ['id'])
    succ_obj.predecessors = [pred_obj]
    _db.session.commit()

    # The successor (child) CAN be completed first - no blockers
    rv_child = client.patch(f"/api/tasks/{succ_obj.id}", json={'status': 'DONE'})
    assert rv_child.status_code == 200, f"Child should be completable first: {rv_child.get_json()}"

    # Now the predecessor (parent) can be completed since child is done
    rv_parent = client.patch(f"/api/tasks/{pred_obj.id}", json={'status': 'DONE'})
    assert rv_parent.status_code == 200


def test_child_can_be_completed_before_parent_predecessor(client, create_user, create_project, create_task, login):
    """Test that children (successors in tree) can be completed even if parent (predecessor) is incomplete.
    
    This is the core requirement: subtasks must close first, then parent can close.
    """
    u = create_user(email='tree_admin@example.com', is_internal=True)
    login(u)
    p = create_project('TreeOrder')
    
    # Create tree: Parent -> Child1, Child2
    parent = create_task(project_id=p['id'], title='TreeParent')
    child1 = create_task(project_id=p['id'], title='TreeChild1')
    child2 = create_task(project_id=p['id'], title='TreeChild2')
    
    from app.models import db as _db
    parent_obj = Task.query.get(parent['id'])
    child1_obj = Task.query.get(child1['id'])
    child2_obj = Task.query.get(child2['id'])
    
    # Link children to parent via predecessors
    child1_obj.predecessors = [parent_obj]
    child2_obj.predecessors = [parent_obj]
    _db.session.commit()

    # Children can be completed even though parent is incomplete
    rv1 = client.patch(f"/api/tasks/{child1_obj.id}", json={'status': 'COMPLETED'})
    assert rv1.status_code == 200, f"Child1 should be completable: {rv1.get_json()}"
    
    rv2 = client.patch(f"/api/tasks/{child2_obj.id}", json={'status': 'COMPLETED'})
    assert rv2.status_code == 200, f"Child2 should be completable: {rv2.get_json()}"

    # Now parent can be completed since all children are done
    rv_parent = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'COMPLETED'})
    assert rv_parent.status_code == 200, f"Parent should be completable now: {rv_parent.get_json()}"


def test_parent_cannot_complete_with_incomplete_successor_children(client, create_user, create_project, create_task, login):
    """Test that parent (predecessor) cannot complete while children (successors) are incomplete."""
    u = create_user(email='block_admin@example.com', is_internal=True)
    login(u)
    p = create_project('BlockTest')
    
    parent = create_task(project_id=p['id'], title='BlockParent')
    child = create_task(project_id=p['id'], title='BlockChild')
    
    from app.models import db as _db
    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])
    
    # Link child to parent
    child_obj.predecessors = [parent_obj]
    _db.session.commit()

    # Parent cannot complete while child is incomplete
    rv = client.patch(f"/api/tasks/{parent_obj.id}", json={'status': 'COMPLETED'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_children' in j
    assert any(c['title'] == 'BlockChild' for c in j['incomplete_children'])
