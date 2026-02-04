import pytest
from unittest.mock import patch
from datetime import datetime

from app.services import license_service
from app.models import License


class MockResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or (payload and str(payload)) or ''

    def json(self):
        return self._payload


def test_activate_tries_api_variants_and_succeeds(db):
    key = 'VAR-KEY-1'
    payload = {
        'success': True,
        'license': {'type': 'STANDARD', 'max_users': 2, 'expires_at': datetime.now().isoformat()}
    }

    # Simulate first two variant URLs returning 404, third returns 200
    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.side_effect = [
            MockResponse(status_code=404, payload={'message': 'Not found'}),
            MockResponse(status_code=404, payload={'message': 'Not found'}),
            MockResponse(status_code=200, payload=payload)
        ]
        res = license_service.activate_license(key)

    assert res.get('success') is True
    assert License.query.filter_by(license_key=key).first() is not None


def test_activate_succeeds_posting_to_base_endpoint(db):
    key = 'BASE-KEY-1'
    payload = {
        'success': True,
        'license': {'type': 'STANDARD', 'max_users': 2, 'expires_at': datetime.now().isoformat()}
    }

    # First attempts to /.../activate return 404, then bare base returns 200
    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.side_effect = [
            MockResponse(status_code=404, payload={'message': 'Not found'}),
            MockResponse(status_code=200, payload=payload)  # this corresponds to bare base
        ]
        res = license_service.activate_license(key)

    assert res.get('success') is True
    assert License.query.filter_by(license_key=key).first() is not None
