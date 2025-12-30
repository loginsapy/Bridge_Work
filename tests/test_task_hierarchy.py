import os
from app.models import Task, Project, db


def test_descendants_includes_children_and_successors(create_project, create_task):
    # Create project and tasks
    p = create_project('H-Test')
    parent = create_task(project_id=p['id'], title='Parent H')
    child = create_task(project_id=p['id'], title='Child H', parent_task_id=None)

    # load objects
    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # simulate predecessor-as-parent relationship
    child_obj.predecessors = [parent_obj]
    db.session.commit()

    # descendants of parent should include the child (via successors or children traversal)
    desc = parent_obj.descendants()
    assert any(d.id == child_obj.id for d in desc)


def test_complete_parent_blocked_by_children(client, create_user, create_project, create_task, login):
    # Setup
    u = create_user(email='h_test_user@example.com', is_internal=True)
    login(u)
    p = create_project('H-Board')
    parent = create_task(project_id=p['id'], title='ParentComplete')
    child = create_task(project_id=p['id'], title='ChildComplete', parent_task_id=parent['id'])

    # Attempt to mark parent as done via API
    rv = client.patch(f"/api/tasks/{parent['id']}", json={'status': 'DONE'})
    assert rv.status_code == 400
    j = rv.get_json()
    assert 'incomplete_children' in j
    assert isinstance(j['incomplete_children'], list)
    assert j['incomplete_children'][0]['id'] == child['id']
