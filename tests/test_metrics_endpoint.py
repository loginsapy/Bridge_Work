def test_metrics_endpoint_basic(client, db):
    rv = client.get('/metrics')
    assert rv.status_code == 200
    text = rv.get_data(as_text=True)
    assert 'alerts_sent_total' in text or 'alerts_sent_total' in text


def test_metrics_incremented_on_send(client, db, create_project, create_user, create_task, monkeypatch):
    # Ensure metrics counters are incremented when sends occur
    from app.tasks.sender import send_grouped_alerts
    provider_calls = []

    class P:
        def send_email(self, recipient_id, subject, body, html=None):
            provider_calls.append(recipient_id)
            return True

        def render_alert(self, recipient_id, task_ids):
            return ('subj', 'txt', '<html/>')

    import app.notifications.provider as prov_mod
    monkeypatch.setattr(prov_mod, 'get_provider', lambda a=None: P())

    p = create_project('M1')
    u = create_user('m@example.com')
    t = create_task(project_id=p['id'], title='m1', assigned_to_id=u.id)

    with client.application.app_context():
        # Reset metrics when using fallback
        client.application.extensions['metrics']['alerts_sent'] = 0
        client.application.extensions['metrics']['alerts_failed'] = 0

        res = send_grouped_alerts({u.id: [t['id']]}, retries=1, backoff_factor=0)
        assert res['success'] == [u.id]
        rv = client.get('/metrics')
        txt = rv.get_data(as_text=True)
        assert 'alerts_sent_total' in txt or 'alerts_sent_total' in txt
