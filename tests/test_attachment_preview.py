from io import BytesIO
from app.models import TaskAttachment, Role, AuditLog


def _make_attachment(client, create_user, create_project, create_task, login, filename='file.pdf', data=b'pdfdata'):
    # helper to upload an attachment and return the model
    user = create_user(email='attachuser@example.com', is_internal=True)
    login(user)
    proj = create_project(name='AttachProj')
    task = create_task(project_id=proj['id'], title='AttachTask')

    filedata = {'file': (BytesIO(data), filename)}
    rv = client.post(f"/task/{task['id']}/upload", data=filedata, content_type='multipart/form-data', follow_redirects=True)
    assert rv.status_code == 200
    at = TaskAttachment.query.filter_by(task_id=task['id']).first()
    assert at is not None
    return at, task


def test_preview_and_download_headers(client, db, create_user, create_project, create_task, login):
    # upload an attachment and then request download with/without inline
    att, task = _make_attachment(client, create_user, create_project, create_task, login, filename='test.pdf', data=b'%PDF-1.4')

    # regular download should force attachment
    rv = client.get(f"/attachment/{att.id}/download")
    assert rv.status_code == 200
    cd = rv.headers.get('Content-Disposition', '')
    assert 'attachment' in cd.lower()
    assert 'inline' not in cd.lower()

    # request with inline=1 to preview
    rv2 = client.get(f"/attachment/{att.id}/download?inline=1")
    assert rv2.status_code == 200
    cd2 = rv2.headers.get('Content-Disposition', '')
    assert 'inline' in cd2.lower()
    assert 'attachment' not in cd2.lower()
    # ensure detail and edit pages include preview markup
    rv_detail = client.get(f"/task/{task.id}")
    assert 'showAttachmentPreview' in rv_detail.get_data(as_text=True)
    assert '?inline=1' in rv_detail.get_data(as_text=True)
    rv_edit = client.get(f"/task/{task.id}/edit")
    assert 'showAttachmentPreview' in rv_edit.get_data(as_text=True)
    assert '?inline=1' in rv_edit.get_data(as_text=True)

def test_preview_not_allowed_for_unauthorized(client, db, create_user, create_project, create_task, login):
    # upload as internal user
    att, task = _make_attachment(client, create_user, create_project, create_task, login)

    # log in as a different external user without access
    other = create_user(email='other@example.com', is_internal=False)
    login(other)

    rv = client.get(f"/attachment/{att.id}/download?inline=1", follow_redirects=True)
    # should redirect or flash error
    assert rv.status_code in (302, 403)
    # optionally check message appears
    text = rv.get_data(as_text=True)
    assert 'permiso' in text or 'Permiso' in text


def test_delete_permissions_and_audit(client, db, create_user, create_project, create_task, login):
    # uploader is a participant (not PMP/Admin)
    part = create_user(email='part@example.com', is_internal=True)
    # ensure role is "Participante"
    from app.models import Role
    prot = Role(name='Participante')
    db.session.add(prot)
    db.session.commit()
    part.role = prot
    db.session.commit()
    login(part)

    proj = create_project(name='DelProj')
    task = create_task(project_id=proj['id'], title='DelTask')
    # upload attachment
    filedata = {'file': (BytesIO(b'hi'), 'one.txt')}
    rv = client.post(f"/task/{task['id']}/upload", data=filedata, content_type='multipart/form-data', follow_redirects=True)
    assert rv.status_code == 200
    att = TaskAttachment.query.filter_by(task_id=task['id']).first()
    assert att is not None

    # uploader may delete - button should be visible on detail page
    rv_page = client.get(f"/task/{task.id}")
    assert 'fa-trash' in rv_page.get_data(as_text=True)
    rv2 = client.delete(f"/api/attachments/{att.id}")
    assert rv2.status_code == 200
    al = AuditLog.query.filter_by(entity_type='task_attachment', entity_id=att.id).first()
    assert al is not None
    assert al.action == 'DELETE'
    assert al.user_id == part.id

    # add another attachment for further tests
    login(part)
    filedata = {'file': (BytesIO(b'hi'), 'two.txt')}
    client.post(f"/task/{task['id']}/upload", data=filedata, content_type='multipart/form-data', follow_redirects=True)
    att2 = TaskAttachment.query.filter_by(task_id=task['id']).order_by(TaskAttachment.id.desc()).first()
    assert att2 is not None

    # different internal non-PMP can't delete
    other = create_user(email='otherint@example.com', is_internal=True)
    otherrole = Role.query.filter_by(name='Participante').first()
    other.role = otherrole
    db.session.commit()
    login(other)
    # should not see delete icon
    rv_other_page = client.get(f"/task/{task.id}")
    assert 'fa-trash' not in rv_other_page.get_data(as_text=True)
    rv3 = client.delete(f"/api/attachments/{att2.id}")
    assert rv3.status_code == 403

    # PMP can delete any
    pmp = create_user(email='pmp@example.com', is_internal=True)
    login(pmp)
    # PMP should see delete icon regardless of uploader
    rv_pmp_page = client.get(f"/task/{task.id}")
    assert 'fa-trash' in rv_pmp_page.get_data(as_text=True)
    rv4 = client.delete(f"/api/attachments/{att2.id}")
    assert rv4.status_code == 200
    al2 = AuditLog.query.filter_by(entity_type='task_attachment', entity_id=att2.id).first()
    assert al2 is not None and al2.user_id == pmp.id
