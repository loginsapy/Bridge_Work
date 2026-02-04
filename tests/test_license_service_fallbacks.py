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


def test_activate_fallback_success(db):
    key = 'FB-KEY-1'
    payload = {
        'success': True,
        'license': {
            'type': 'STANDARD',
            'max_users': 5,
            'features': {'x': True},
            'customer_email': 'a@b.c',
            'expires_at': datetime.now().isoformat()
        }
    }

    # First call returns 404, second returns 200
    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.side_effect = [MockResponse(status_code=404, payload={'message':'Recurso no encontrado'}, text='Recurso no encontrado'), MockResponse(status_code=200, payload=payload)]
        res = license_service.activate_license(key)

    assert res.get('success') is True
    lic = License.query.filter_by(license_key=key).first()
    assert lic is not None
    assert lic.status == 'ACTIVE'


def test_activate_all_variants_404(db):
    key = 'FB-KEY-2'
    with patch('app.services.license_service.requests.post') as mock_post:
        # Always 404
        mock_post.return_value = MockResponse(status_code=404, payload={'message':'Not found'}, text='Not found')
        res = license_service.activate_license(key)

    assert res.get('success') is False
    assert res.get('error_code') == 'resource_not_found'
    assert res.get('http_status') == 404
