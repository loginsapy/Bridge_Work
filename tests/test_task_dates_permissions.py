from datetime import datetime


def test_client_cannot_modify_dates(client, db, create_user, create_project, create_task, login):
    # Create an external client user
    client_user = create_user(email='cli@example.com', is_internal=False)
    login(client_user)

    p = create_project(name='CliP')
    t = create_task(project_id=p['id'], title='Task')

    rv = client.patch(f"/api/tasks/{t['id']}", json={'due_date': '2026-01-01T00:00:00'})
    assert rv.status_code == 403


def test_internal_non_pmp_cannot_modify_dates(client, db, create_user, create_project, create_task, login):
    # Create an internal user but assign non-PMP role
    u = create_user(email='dev@example.com', is_internal=True)
    from app.models import Role
    dev_role = Role(name='Developer')
    db.session.add(dev_role)
    db.session.commit()
    u.role = dev_role
    db.session.commit()

    login(u)
    p = create_project(name='DevP')
    t = create_task(project_id=p['id'], title='DevTask')

    rv = client.patch(f"/api/tasks/{t['id']}", json={'start_date': '2026-02-02T00:00:00'})
    assert rv.status_code == 403


def test_pmp_can_modify_dates(client, db, create_user, create_project, create_task, login):
    # Default internal user created by fixture becomes PMP role
    u = create_user(email='pmp@example.com', is_internal=True)
    login(u)

    p = create_project(name='PmpP')
    t = create_task(project_id=p['id'], title='PmpTask')

    rv = client.patch(f"/api/tasks/{t['id']}", json={'due_date': '2026-03-03T00:00:00'})
    assert rv.status_code == 200

    # Verify the due_date was updated
    rv2 = client.get(f"/api/tasks/{t['id']}")
    assert rv2.status_code == 200
    data = rv2.get_json()
    assert data.get('due_date') is not None


def test_non_pmp_cannot_edit_dates_via_form(client, db, create_user, create_project, create_task, login):
    u = create_user(email='dev2@example.com', is_internal=True)
    from app.models import Role
    drole = Role(name='Developer')
    db.session.add(drole)
    db.session.commit()
    u.role = drole
    db.session.commit()

    login(u)
    p = create_project(name='FormP')
    t = create_task(project_id=p['id'], title='FormTask')

    rv = client.post(f"/task/{t['id']}/edit", data={'title': 'FormTask', 'due_date': '2026-04-04T00:00'}, follow_redirects=True)
    assert rv.status_code == 200
    # Ensure flash message says no permission or that due_date wasn't set by checking task retrieval
    rv2 = client.get(f"/api/tasks/{t['id']}")
    assert rv2.status_code == 200
    json = rv2.get_json()
    assert json.get('due_date') is None
