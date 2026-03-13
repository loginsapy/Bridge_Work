"""Tests for webhook CRUD API and dispatch logic."""
import pytest
import json


def _pmp(create_user):
    return create_user(email='pmp@wh.test', is_internal=True)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_webhook(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'Slack Dev',
        'url': 'https://hooks.slack.com/test/xyz',
        'events': ['task.created', 'task.completed'],
        'active': True,
    })
    assert rv.status_code == 201
    data = rv.get_json()
    assert data['name'] == 'Slack Dev'
    assert 'id' in data


def test_list_webhooks(client, db, create_user, login):
    login(_pmp(create_user))
    client.post('/api/webhooks', json={
        'name': 'WH1', 'url': 'https://example.com/hook', 'events': ['task.created']
    })
    rv = client.get('/api/webhooks')
    assert rv.status_code == 200
    assert len(rv.get_json()['webhooks']) >= 1


def test_update_webhook(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'Old Name', 'url': 'https://example.com/hook', 'events': ['task.created']
    })
    wh_id = rv.get_json()['id']

    rv2 = client.put(f'/api/webhooks/{wh_id}', json={
        'name': 'New Name', 'url': 'https://example.com/hook',
        'events': ['task.completed'], 'active': False,
    })
    assert rv2.status_code == 200
    assert rv2.get_json()['name'] == 'New Name'
    assert rv2.get_json()['active'] is False


def test_delete_webhook(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'To Delete', 'url': 'https://example.com/del', 'events': ['task.created']
    })
    wh_id = rv.get_json()['id']

    rv_del = client.delete(f'/api/webhooks/{wh_id}')
    assert rv_del.status_code == 200

    # Verify gone
    rv_list = client.get('/api/webhooks')
    ids = [w['id'] for w in rv_list.get_json()['webhooks']]
    assert wh_id not in ids


def test_delete_nonexistent_webhook_returns_404(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.delete('/api/webhooks/nonexistent-id-123')
    assert rv.status_code == 404


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_webhook_crud_requires_login(client, db):
    rv = client.get('/api/webhooks')
    assert rv.status_code in (401, 302)

    rv2 = client.post('/api/webhooks', json={'name': 'x', 'url': 'http://x.com', 'events': []})
    assert rv2.status_code in (401, 302)


# ── Dispatch (unit-level) ─────────────────────────────────────────────────────

def test_dispatch_unknown_event_is_no_op(app, db):
    """dispatch() with unknown event should not raise."""
    with app.app_context():
        from app.services import webhook_service
        # Should not raise
        webhook_service.dispatch('event.unknown', {'task_id': 1})


def test_dispatch_calls_active_webhooks(app, db, monkeypatch):
    """dispatch() fires threads only for active webhooks matching the event."""
    calls = []

    def fake_send(webhook, event, data):
        calls.append((webhook['name'], event))

    with app.app_context():
        from app.services import webhook_service

        # Inject two fake webhooks: one active+matching, one inactive
        fake_webhooks = [
            {'id': 'a', 'name': 'Active', 'url': 'https://example.com/a',
             'events': ['task.created'], 'active': True, 'secret': ''},
            {'id': 'b', 'name': 'Inactive', 'url': 'https://example.com/b',
             'events': ['task.created'], 'active': False, 'secret': ''},
        ]
        monkeypatch.setattr(webhook_service, '_load_webhooks', lambda: fake_webhooks)
        monkeypatch.setattr(webhook_service, '_send_one', fake_send)

        # Use threading.Thread mock to run synchronously
        import threading
        original_thread = threading.Thread

        class SyncThread:
            def __init__(self, target, args, **kwargs):
                self._target = target
                self._args = args
            def start(self):
                self._target(*self._args)

        monkeypatch.setattr(threading, 'Thread', SyncThread)

        webhook_service.dispatch('task.created', {'task_id': 1, 'task_title': 'T'})

    assert len(calls) == 1
    assert calls[0] == ('Active', 'task.created')


def test_dispatch_task_created_on_api_create(client, db, create_user, create_project, login, monkeypatch):
    """Creating a task via API triggers task.created webhook dispatch."""
    dispatched = []

    import app.services.webhook_service as ws
    monkeypatch.setattr(ws, 'dispatch', lambda event, data: dispatched.append(event))

    pmp = _pmp(create_user)
    login(pmp)
    proj = create_project(name='Dispatch Proj')

    rv = client.post('/api/tasks', json={'project_id': proj['id'], 'title': 'New Task'})
    assert rv.status_code == 201
    assert 'task.created' in dispatched


def test_slack_payload_format():
    """_build_slack_payload returns correct Slack attachment structure."""
    from app.services.webhook_service import _build_slack_payload
    payload = _build_slack_payload('task.completed', {
        'task_title': 'My Task', 'project_name': 'My Project',
        'user_name': 'Alice', 'new_status': 'COMPLETED',
    })
    assert 'attachments' in payload
    att = payload['attachments'][0]
    assert att['color'] == '#198754'
    assert 'My Task' in att['title']
    assert any(f['title'] == 'Proyecto' for f in att['fields'])


def test_teams_payload_format():
    """_build_teams_payload returns correct Teams MessageCard structure."""
    from app.services.webhook_service import _build_teams_payload
    payload = _build_teams_payload('task.status_changed', {
        'task_title': 'Changed Task', 'new_status': 'IN_REVIEW',
    })
    assert payload['@type'] == 'MessageCard'
    assert 'Changed Task' in payload['summary']


def test_generic_payload_format():
    """_build_generic_payload returns event + timestamp + data."""
    from app.services.webhook_service import _build_generic_payload
    payload = _build_generic_payload('task.assigned', {'task_id': 5})
    assert payload['event'] == 'task.assigned'
    assert 'timestamp' in payload
    assert payload['data']['task_id'] == 5


def test_hmac_signature_format():
    """_build_signature produces sha256= prefixed hex string."""
    from app.services.webhook_service import _build_signature
    sig = _build_signature(b'test-body', 'my-secret')
    assert sig.startswith('sha256=')
    assert len(sig) == 7 + 64  # "sha256=" + 64 hex chars


# ── Security: URL validation (SSRF prevention) ────────────────────────────────

def test_webhook_rejects_localhost_url(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'SSRF', 'url': 'http://localhost/admin', 'events': ['task.created']
    })
    assert rv.status_code == 400
    assert 'inválida' in rv.get_json().get('error', '').lower()


def test_webhook_rejects_private_ip(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'SSRF2', 'url': 'http://192.168.1.100/hook', 'events': ['task.created']
    })
    assert rv.status_code == 400


def test_webhook_rejects_loopback_ip(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'SSRF3', 'url': 'http://127.0.0.1:8080/secret', 'events': ['task.created']
    })
    assert rv.status_code == 400


def test_webhook_rejects_non_http_scheme(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'BadScheme', 'url': 'ftp://example.com/hook', 'events': ['task.created']
    })
    assert rv.status_code == 400


def test_webhook_accepts_valid_https_url(client, db, create_user, login):
    login(_pmp(create_user))
    rv = client.post('/api/webhooks', json={
        'name': 'ValidHTTPS', 'url': 'https://hooks.example.com/prod/xyz',
        'events': ['task.created'], 'active': True,
    })
    assert rv.status_code == 201
