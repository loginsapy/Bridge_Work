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

    class MockMSAL:
        def __init__(self):
            self.calls = 0
        def get_authorization_request_url(self, scopes, redirect_uri=None):
            self.calls += 1
            # Simulate first call raising ValueError (tenant rejects reserved scopes), second call succeeds
            if self.calls == 1:
                raise ValueError("You cannot use any scope value that is reserved")
            return 'https://login.example/authorize'

        def acquire_token_by_authorization_code(self, code, scopes=None, redirect_uri=None):
            # Return id token claims to simulate a successful token acquisition
            return {'id_token_claims': {'oid': 'oid-123', 'preferred_username': 'newuser@example.com', 'given_name': 'New', 'family_name': 'User'}}

    # Patch the function used by the auth routes module
    monkeypatch.setattr('app.auth.routes.get_msal_app', lambda: MockMSAL())

    client = app.test_client()

    with app.app_context():
        db.create_all()
        print('USERS BEFORE:', User.query.all())
        # Start SSO flow (should redirect to auth URL even if the initial scope set caused a fallback)
        resp = client.post('/auth/login', data={'action': 'sso'})
        assert resp.status_code in (302, 303)

        # Simulate callback with code
        resp = client.get('/auth/callback?code=abc123')
        print('CALLBACK RESP STATUS:', resp.status_code)
        print('USERS AFTER:', User.query.all())
        # After callback, user should exist in DB
        user = User.query.filter_by(azure_oid='oid-123').first()
        assert user is not None
        assert user.is_internal
        assert user.email == 'newuser@example.com'
