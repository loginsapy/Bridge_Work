import os
from unittest.mock import Mock

from app import create_app, db
from app.models import User


def test_oidc_jit_provisioning(monkeypatch):
    # Ensure an in-memory DB for test
    # Use a file-based SQLite DB so schema and sessions persist across requests during tests
    os.environ['DATABASE_URL'] = 'sqlite:///test.db'
    # ensure a clean DB file for the test
    if os.path.exists('test.db'):
        os.remove('test.db')
    app = create_app('config.DevConfig')
    app.config['TESTING'] = True

    import base64, json

    class MockMSAL:
        def __init__(self):
            pass
        def get_authorization_request_url(self, scopes, redirect_uri=None):
            return 'https://login.example/authorize'

        def acquire_token_by_authorization_code(self, code, scopes=None, redirect_uri=None):
            # Build a fake id_token with payload claims
            payload = {'oid': 'oid-123', 'preferred_username': 'newuser@example.com', 'given_name': 'New', 'family_name': 'User', 'email': 'newuser@example.com'}
            b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
            fake_id_token = f'header.{b64}.sig'
            return {'access_token': 'fake-access-token', 'id_token': fake_id_token}

    # Patch ConfidentialClientApplication used in the callback and Graph photo request
    monkeypatch.setattr('app.auth.routes.ConfidentialClientApplication', lambda *args, **kwargs: MockMSAL())

    # Mock Graph photo response to return an image bytes
    class DummyResp:
        status_code = 200
        headers = {'Content-Type': 'image/jpeg'}
        content = b'\xff\xd8\xff\xdbfakejpegbytes'
    monkeypatch.setattr('app.auth.routes.requests.get', lambda url, headers=None, timeout=None: DummyResp())

    client = app.test_client()

    with app.app_context():
        db.create_all()

        # Simulate callback with code (bypassing the initial /auth/login redirect)
        resp = client.get('/auth/callback?code=abc123', follow_redirects=True)
        assert resp.status_code == 200

        # After callback, user should exist in DB and photo should be saved
        user = User.query.filter_by(azure_oid='oid-123').first()
        assert user is not None
        assert user.is_internal
        assert user.email == 'newuser@example.com'
        assert user.photo is not None
        assert user.photo_mime == 'image/jpeg'

        # The photo endpoint should serve the binary
        photo_resp = client.get(f'/user/{user.id}/photo')
        assert photo_resp.status_code == 200
        assert photo_resp.data.startswith(b'\xff\xd8')
        assert photo_resp.headers.get('Content-Type') == 'image/jpeg'
