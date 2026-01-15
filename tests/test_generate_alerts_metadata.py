from datetime import datetime, timedelta
from app.tasks.alerts import generate_alerts
from app.models import SystemSettings


def test_generate_alerts_updates_last_run_meta(client, db, create_project, create_user, create_task):
    p = create_project(name='Meta')
    u = create_user(email='meta@example.com')
    tomorrow = (datetime.now() + timedelta(days=1))
    create_task(project_id=p['id'], title='meta_task', is_external_visible=False, due_date=tomorrow, assigned_to_id=u.id)

    res = generate_alerts(cutoff_days=2)
    assert 'created' in res

    # Check SystemSettings metadata
    assert SystemSettings.get('last_due_reminder_run') is not None
    assert int(SystemSettings.get('last_due_reminder_created', 0)) >= 0
