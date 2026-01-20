from io import BytesIO
from app import db


def test_participant_cannot_change_title_but_can_change_status_and_upload(client, create_user, create_project, create_task, login):
    # Create participant user
    participant = create_user(email='part@example.com', is_internal=True)
    from app.models import Role
    part_role = Role(name='Participante')
    db.session.add(part_role)
    db.session.commit()
    participant.role = part_role
    db.session.commit()

    login(participant)

    p = create_project(name='PartP')
    t = create_task(project_id=p['id'], title='Original')

    # Attempt to change title (should be rejected)
    rv = client.post(f"/task/{t['id']}/edit", data={'title': 'Hacked'}, follow_redirects=True)
    assert rv.status_code == 200
    # Confirm title unchanged
    from app.models import Task
    task = Task.query.get(t['id'])
    assert task.title == 'Original'

    # Can change status
    rv2 = client.post(f"/task/{t['id']}/edit", data={'status': 'COMPLETED'}, follow_redirects=True)
    assert rv2.status_code == 200
    task = Task.query.get(t['id'])
    assert task.status == 'COMPLETED'

    # Can upload attachments
    filedata = {'attachments': (BytesIO(b'hi'), 'hello.txt')}
    rv3 = client.post(f"/task/{t['id']}/edit", data=filedata, content_type='multipart/form-data', follow_redirects=True)
    assert rv3.status_code == 200
    task = Task.query.get(t['id'])
    assert len(task.attachments) == 1

    # Attempt to change restricted fields via form (should be blocked)
    rv4 = client.post(f"/task/{t['id']}/edit", data={'estimated_hours': '100', 'parent_task_id': '', 'predecessor_ids': []}, follow_redirects=True)
    assert rv4.status_code == 200
    task = Task.query.get(t['id'])
    assert task.estimated_hours is None


def test_client_limited_edit_behavior(client, create_user, create_project, create_task, login):
    # Client user (external) who is project client
    client_user = create_user(email='client1@example.com', is_internal=False)

    # Create project with client assigned
    p = create_project(name='ClientP', client_id=client_user.id)
    # Create task in project
    t = create_task(project_id=p['id'], title='Ctask')

    login(client_user)

    # Attempt to change priority (should be rejected)
    rv = client.post(f"/task/{t['id']}/edit", data={'priority': 'CRITICAL'}, follow_redirects=True)
    assert rv.status_code == 200
    from app.models import Task
    task = Task.query.get(t['id'])
    assert task.priority != 'CRITICAL'

    # Client can change status
    rv2 = client.post(f"/task/{t['id']}/edit", data={'status': 'IN_PROGRESS'}, follow_redirects=True)
    assert rv2.status_code == 200
    task = Task.query.get(t['id'])
    assert task.status == 'IN_PROGRESS'

    # Attempt to change restricted fields via form (should be blocked)
    rv3 = client.post(f"/task/{t['id']}/edit", data={'estimated_hours': '50', 'priority': 'CRITICAL', 'parent_task_id': ''}, follow_redirects=True)
    assert rv3.status_code == 200
    task = Task.query.get(t['id'])
    assert task.estimated_hours is None
    assert task.priority != 'CRITICAL'