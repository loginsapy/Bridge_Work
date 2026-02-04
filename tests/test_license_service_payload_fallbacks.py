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


def test_activate_payload_fallback_success(db):
    key = 'ALT-KEY-1'
    payload = {
        'success': True,
        'license': {'type': 'STANDARD', 'max_users': 1, 'expires_at': datetime.now().isoformat()}
    }

    # Simulate: initial variant calls -> 404, then alternate payload succeeds (200)
    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.side_effect = [
            MockResponse(status_code=404, payload={'message': 'Not found'}),  # first URL try
            MockResponse(status_code=404, payload={'message': 'Not found'}),  # second URL try
            MockResponse(status_code=200, payload=payload)  # success when using alt payload
        ]
        res = license_service.activate_license(key)

    assert res.get('success') is True
    assert License.query.filter_by(license_key=key).first() is not None


def test_activate_all_payloads_404_returns_resource_not_found(db):
    key = 'ALT-KEY-2'
    with patch('app.services.license_service.requests.post') as mock_post:
        # All attempts return 404
        mock_post.return_value = MockResponse(status_code=404, payload={'message': 'Not found'})
        res = license_service.activate_license(key)

    assert res.get('success') is False
    assert res.get('error_code') == 'resource_not_found'
    assert res.get('http_status') == 404
