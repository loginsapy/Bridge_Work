from datetime import datetime, timedelta
from app.tasks.alerts import generate_alerts


def test_generate_alerts_creates_alert_log(client, db, create_project, create_user, create_task):
    # Setup: project, user, and a task due tomorrow
    p = create_project(name='A1')
    u = create_user(email='a1@example.com')
    tomorrow = (datetime.now() + timedelta(days=1))
    task = create_task(project_id=p['id'], title='due_task', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)

    result = generate_alerts(cutoff_days=2)
    assert len(result['created']) == 1

    # Ensure the AlertLog is persisted
    from app.models import AlertLog
    logs = AlertLog.query.all()
    assert len(logs) == 1
    assert logs[0].task_id == task['id']


def test_generate_alerts_is_idempotent_within_window(client, db, create_project, create_user, create_task):
    p = create_project(name='A2')
    u = create_user(email='a2@example.com')
    tomorrow = (datetime.now() + timedelta(days=1))
    task = create_task(project_id=p['id'], title='due_task_2', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)

    first = generate_alerts(cutoff_days=2)
    assert len(first['created']) == 1

    second = generate_alerts(cutoff_days=2)
    # Should not create another alert within idempotency window
    assert len(second['created']) == 0


def test_generate_alerts_groups_by_recipient(client, db, create_project, create_user, create_task):
    p = create_project(name='A3')
    u = create_user(email='group@example.com')
    tomorrow = (datetime.now() + timedelta(days=1))
    t1 = create_task(project_id=p['id'], title='g1', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)
    t2 = create_task(project_id=p['id'], title='g2', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)

    res = generate_alerts(cutoff_days=2)
    assert len(res['created']) == 2
    groups = res['groups']
    assert u.id in groups
    assert set(groups[u.id]) == {t1['id'], t2['id']}
