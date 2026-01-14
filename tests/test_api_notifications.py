def test_api_update_task_sends_notifications(client, db, create_user, create_project, login, monkeypatch):
    # Create admin and client users
    admin = create_user(email='api_admin@example.com', is_internal=True)
    client_user = create_user(email='api_client@example.com', is_internal=False)

    # Create project and attach client
    p = create_project(name='P-api-notify')
    from app.models import Project, db as _db, Task
    proj = Project.query.get(p['id'])
    proj.clients.append(client_user)
    _db.session.commit()

    # Create task without assigned client
    t = Task(project_id=proj.id, title='T-API-Notify')
    _db.session.add(t)
    _db.session.commit()

    # Login as admin
    login(admin)

    calls = []
    def fake_notify(task, assigned_by_user=None, send_email=False, notify_client=False):
        calls.append((task.id, notify_client, send_email))
        return True

    from app.services.notifications import NotificationService
    monkeypatch.setattr(NotificationService, 'notify_task_assigned', staticmethod(fake_notify))

    # Update via API to assign client
    rv = client.patch(f"/api/tasks/{t.id}", json={'assigned_client_id': client_user.id})
    assert rv.status_code == 200

    # Ensure notify called for client assignment
    assert any(c for c in calls if c[0] == t.id and c[1] is True)
