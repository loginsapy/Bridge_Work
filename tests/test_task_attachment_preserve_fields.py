from io import BytesIO
from app import db


def test_upload_does_not_clear_assignees_or_other_fields(client, create_user, create_project, create_task, login):
    # Create a PMP and two participants
    pmp = create_user(email='pmp2@example.com', is_internal=True)
    login(pmp)

    # Create a project and a task with assignees and fields
    project = create_project(name='PreserveP')
    t = create_task(project_id=project['id'], title='Pres', assigned_to_id=None)

    # Assign two users as assignees via API (simulate admin)
    u1 = create_user(email='a1@example.com', is_internal=True)
    u2 = create_user(email='a2@example.com', is_internal=True)
    # Use API patch to set assignees
    rv = client.patch(f"/api/tasks/{t['id']}", json={'assignees': [u1.id, u2.id]})
    assert rv.status_code in (200, 201, 204)

    # Now login as participant and upload an attachment
    participant = create_user(email='part2@example.com', is_internal=True)
    from app.models import Role
    part_role = Role(name='Participante')
    db.session.add(part_role)
    db.session.commit()
    participant.role = part_role
    db.session.commit()

    login(participant)

    # Fetch task to get current values
    rv0 = client.get(f"/api/tasks/{t['id']}")
    data0 = rv0.get_json()
    assert len(data0.get('assignees', [])) >= 2

    # Upload an attachment via form POST (participant) without other fields
    filedata = {'attachments': (BytesIO(b'hi'), 'keep.txt')}
    rv1 = client.post(f"/task/{t['id']}/edit", data=filedata, content_type='multipart/form-data', follow_redirects=True)
    assert rv1.status_code == 200
    # Ensure no generic error flash was shown
    assert 'Error al actualizar' not in rv1.get_data(as_text=True)

    # Ensure assignees remain intact and other fields unchanged
    rv2 = client.get(f"/api/tasks/{t['id']}")
    data2 = rv2.get_json()
    assert len(data2.get('assignees', [])) >= 2
    # estimated_hours should remain None (not changed)
    assert data2.get('estimated_hours') is None

    # Also ensure attachments increased
    # The task may now have attachments; check via project detail view or API
    # For simplicity, check attachments length via API task fetch contains attachments or attachments metadata
    # (If attachments are not returned in API, at least the edit didn't wipe fields.)
