import base64
import json

from app.models import User


def test_oidc_jit_provisioning(client, db, monkeypatch):
    class MockMSAL:
        def get_authorization_request_url(self, scopes, redirect_uri=None):
            return 'https://login.example/authorize'

        def acquire_token_by_authorization_code(self, code, scopes=None, redirect_uri=None):
            payload = {
                'oid': 'oid-123',
                'preferred_username': 'newuser@example.com',
                'given_name': 'New',
                'family_name': 'User',
                'email': 'newuser@example.com',
            }
            b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
            return {'access_token': 'fake-access-token', 'id_token': f'header.{b64}.sig'}

    monkeypatch.setattr('app.auth.routes.ConfidentialClientApplication', lambda *args, **kwargs: MockMSAL())

    class DummyResp:
        status_code = 200
        headers = {'Content-Type': 'image/jpeg'}
        content = b'\xff\xd8\xff\xdbfakejpegbytes'

    monkeypatch.setattr('app.auth.routes.requests.get', lambda url, headers=None, timeout=None: DummyResp())

    resp = client.get('/auth/callback?code=abc123', follow_redirects=True)
    assert resp.status_code == 200

    user = User.query.filter_by(azure_oid='oid-123').first()
    assert user is not None
    assert user.is_internal
    assert user.email == 'newuser@example.com'
    assert user.photo is not None
    assert user.photo_mime == 'image/jpeg'

    photo_resp = client.get(f'/user/{user.id}/photo')
    assert photo_resp.status_code == 200
    assert photo_resp.data.startswith(b'\xff\xd8')
    assert photo_resp.headers.get('Content-Type') == 'image/jpeg'
