def test_admin_sees_task_preselected(client, db, create_user, create_project, create_task, login):
    # Admin user should see preselected task
    admin = create_user(email='adm_tp@example.com', is_internal=True)
    login(admin)
    p = create_project(name='P-admin-pre')
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'AdminTask', 'submit': 'Create'}, follow_redirects=True)
    assert rv.status_code == 200
    rv2 = client.get(f"/api/tasks?project_id={p['id']}")
    t = rv2.get_json()['items'][0]

    rv3 = client.get(f"/time-entries/new?task_id={t['id']}")
    assert rv3.status_code == 200
    html = rv3.get_data(as_text=True)
    assert f'<option value="{t["id"]}"' in html
    assert 'selected' in html.split(f'<option value="{t["id"]}"')[1].split('>')[0]


def test_pmp_sees_task_preselected(client, db, create_user, create_project, create_task, login):
    # PMP role should preselect as well (create_user defaults to PMP for internal users)
    pmp = create_user(email='pmp_tp@example.com', is_internal=True)
    login(pmp)
    p = create_project(name='P-pmp-pre')
    rv = client.post('/task', data={'project_id': p['id'], 'title': 'PMPTask', 'submit': 'Create'}, follow_redirects=True)
    assert rv.status_code == 200
    rv2 = client.get(f"/api/tasks?project_id={p['id']}")
    t = rv2.get_json()['items'][0]

    rv3 = client.get(f"/time-entries/new?task_id={t['id']}")
    assert rv3.status_code == 200
    html = rv3.get_data(as_text=True)
    assert f'<option value="{t["id"]}"' in html
    assert 'selected' in html.split(f'<option value="{t["id"]}"')[1].split('>')[0]
