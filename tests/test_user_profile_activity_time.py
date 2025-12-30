from datetime import datetime

def test_user_profile_shows_activity_timestamp(client, db, create_user, create_project, create_task, login):
    # Setup
    u = create_user(email='actuser@example.com', is_internal=True)
    login(u)
    p = create_project(name='P-activity')
    t = create_task(project_id=p['id'], title='ActivityTask', assigned_to_id=u.id)

    # Add an audit log as recent activity
    from app.models import AuditLog, db
    ts = datetime(2025, 1, 2, 15, 30)
    audit = AuditLog(entity_type='Task', entity_id=t['id'], action='UPDATE', user_id=u.id, changes={'dummy': {'old': None, 'new': 'x'}}, created_at=ts)
    db.session.add(audit)
    db.session.commit()

    rv = client.get(f"/user/{u.id}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert '02/01/2025 15:30' in html