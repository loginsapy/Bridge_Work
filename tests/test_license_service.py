import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from app.services import license_service
from app.models import License


class MockResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload) if payload else ''

    def json(self):
        return self._payload


from sqlalchemy import inspect

def test_licenses_table_exists(db):
    # The models should create a table named 'licenses'
    assert inspect(db.engine).has_table('licenses')


def test_activate_license_success(db):
    key = 'TEST-KEY-1234'

    payload = {
        'success': True,
        'license': {
            'type': 'STANDARD',
            'max_users': 10,
            'features': {'feature_x': True},
            'customer_name': 'Test Customer',
            'customer_email': 'cust@example.com',
            'expires_at': (datetime.now() + timedelta(days=30)).isoformat()
        }
    }

    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.return_value = MockResponse(status_code=200, payload=payload)
        result = license_service.activate_license(key)

    assert result.get('success') is True
    # License record persisted
    lic = License.query.filter_by(license_key=key).first()
    assert lic is not None
    assert lic.status == 'ACTIVE'
    assert lic.license_type == 'STANDARD'
    assert lic.customer_email == 'cust@example.com'


def test_validate_license_success(db):
    # Create a license entry
    lic = License(license_key='VAL-KEY-1', status='ACTIVE')
    db.session.add(lic)
    db.session.commit()

    payload = {
        'valid': True,
        'license': {
            'expires_at': (datetime.now() + timedelta(days=60)).isoformat()
        }
    }

    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.return_value = MockResponse(status_code=200, payload=payload)
        result = license_service.validate_license(lic)

    assert result.get('valid') is True
    refreshed = License.query.filter_by(license_key='VAL-KEY-1').first()
    assert refreshed.last_validated_at is not None


def test_deactivate_license_success(db):
    lic = License(license_key='DEL-KEY-1', status='ACTIVE')
    db.session.add(lic)
    db.session.commit()

    payload = {'success': True, 'message': 'Desactivada'}

    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.return_value = MockResponse(status_code=200, payload=payload)
        result = license_service.deactivate_license()

    assert result.get('success') is True
    updated = License.query.filter_by(license_key='DEL-KEY-1').first()
    assert updated.status == 'INACTIVE'


def test_activate_license_invalid(db):
    key = 'BAD-KEY-1'
    payload = {'success': False, 'message': 'Clave inválida'}
    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.return_value = MockResponse(status_code=400, payload=payload)
        result = license_service.activate_license(key)

    assert result.get('success') is False
    assert result.get('error_code') == 'invalid_license'


def test_activate_license_network_error(db):
    key = 'NET-ERR-1'
    with patch('app.services.license_service.requests.post', side_effect=Exception('Connection aborted')):
        result = license_service.activate_license(key)

    assert result.get('success') is False
    assert result.get('error_code') == 'unknown' or result.get('error_code') == 'network'
