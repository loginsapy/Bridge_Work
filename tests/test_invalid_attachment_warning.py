from io import BytesIO


def test_invalid_extension_shows_warning_and_files_skipped(client, db, create_user, create_project, create_task, login):
    u = create_user(email='warn@example.com', is_internal=True)
    login(u)
    p = create_project(name='WarnP')
    t = create_task(project_id=p['id'], title='WarnTask')

    # Upload valid and invalid files together
    data = {
        'attachments': [
            (BytesIO(b'hello'), 'good.pdf'),
            (BytesIO(b'spam'), 'bad.exe')
        ]
    }
    rv = client.post(f"/task/{t['id']}/edit", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Algunos archivos no fueron subidos porque su extensión no está permitida' in html

    # Ensure only the valid file is present in attachments
    rv2 = client.get(f"/api/tasks/{t['id']}")
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    # attachments may not be returned by API; check on DB via server-side using ORM
    from app.models import Task
    task_obj = Task.query.get(t['id'])
    names = [a.filename for a in task_obj.attachments]
    assert 'good.pdf' in names
    assert 'bad.exe' not in names